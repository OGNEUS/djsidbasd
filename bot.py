import asyncio
import logging
import os
import requests

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

API_TOKEN = os.getenv("API_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MANUAL_PAYMENT_PHONE = os.getenv("MANUAL_PAYMENT_PHONE")
CURRENCY = os.getenv("CURRENCY", "USDT")
SUPPORT = os.getenv("SUPPORT")

if not all([API_TOKEN, CRYPTOBOT_TOKEN, MANUAL_PAYMENT_PHONE, SUPPORT]):
    raise ValueError("❌ Не все переменные окружения заданы в .env! Проверь файл .env")

PREMIUM_PACKAGES = {3: 1030, 6: 1400, 12: 2500}
STAR_PRICE_PER_UNIT = 1.4
STAR_PACKAGES = {
    50: 70, 100: 140, 200: 280, 300: 420, 400: 560,
    500: 700, 600: 840, 700: 980, 800: 1120, 900: 1260,
}
TON_PRICE = 1.62

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class OrderStates(StatesGroup):
    waiting_amount = State()
    waiting_username = State()
    waiting_payment = State()
    waiting_manual_payment = State()

def get_usdt_rate_coingecko() -> float:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "tether", "vs_currencies": "rub"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "tether" in data and "rub" in data["tether"]:
            rate = float(data["tether"]["rub"])
            logging.info(f"CoinGecko USDT/RUB rate: {rate}")
            return rate
    except Exception as e:
        logging.error(f"Ошибка получения курса с CoinGecko: {e}")
    logging.warning("Используем fallback курс 90 RUB за 1 USDT")
    return 90.0


def create_cryptobot_invoice(amount_usdt: float, description: str):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "amount": str(round(amount_usdt, 4)),
        "asset": CURRENCY,
        "description": description[:1024],
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        logging.error(f"Ошибка создания инвойса: {e}")
        return {"ok": False}


def get_invoice_status(invoice_id: int):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    params = {"invoice_ids": str(invoice_id)}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        if data.get("ok") and data.get("result"):
            return data["result"][0]["status"]
        return "error"
    except Exception as e:
        logging.error(f"Ошибка проверки статуса: {e}")
        return "error"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = """🚀 Добро пожаловать в StarGram
Здесь ты можешь быстро и безопасно купить:
⭐ Звёзды Telegram
💎 Telegram Premium
💠 TON (криптовалюта)
⚡ Мгновенная выдача
🔒 Надёжно и без лишних действий
💸 Выгодный курс

Работаем быстро — ты получаешь результат без ожидания 👌
Выбирай нужный раздел и оформляй покупку прямо сейчас!"""

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⭐ Звёзды", callback_data="category:stars"),
        types.InlineKeyboardButton(text="💠 TON", callback_data="category:ton")
    )
    builder.row(types.InlineKeyboardButton(text="💎 Telegram Premium", callback_data="category:premium"))
    builder.row(types.InlineKeyboardButton(text="Поддержка", url=f'https://t.me/{SUPPORT}'))

    await message.answer(text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "cancel")
async def callback_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Оформление заказа отменено.")
    await callback.answer()


@dp.callback_query(F.data.startswith("category:"))
async def callback_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split(":")[1]
    await state.update_data(category=category)

    if category == "stars":
        builder = InlineKeyboardBuilder()
        for stars, price in STAR_PACKAGES.items():
            builder.button(
                text=f"{stars} ⭐ — {price} ₽",
                callback_data=f"option:stars:{stars}:{price}"
            )
        builder.row(types.InlineKeyboardButton(text="🔢 Другое количество звёзд", callback_data="stars:custom"))
        builder.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
        builder.adjust(2)

        await callback.message.edit_text(
            "<b>⭐ Выберите пакет Звёзд Telegram</b>\n\n"
            f"💰 Цена за 1 звезду: <b>{STAR_PRICE_PER_UNIT} ₽</b>",
            reply_markup=builder.as_markup()
        )

    elif category == "premium":
        builder = InlineKeyboardBuilder()
        for months, price in PREMIUM_PACKAGES.items():
            builder.button(
                text=f"{months} месяцев — {price} ₽",
                callback_data=f"option:premium:{months}:{price}"
            )
        builder.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
        builder.adjust(2)

        await callback.message.edit_text(
            "<b>💎 Выберите длительность Telegram Premium</b>",
            reply_markup=builder.as_markup()
        )

    elif category == "ton":
        await callback.message.edit_text("💠 Введите сумму TON для покупки (минимум 0.1 TON):")
        await state.set_state(OrderStates.waiting_amount)

    await callback.answer()


@dp.callback_query(F.data.startswith("option:"))
async def callback_option(callback: types.CallbackQuery, state: FSMContext):
    _, cat, val1, val2 = callback.data.split(":")
    if cat == "stars":
        stars = int(val1)
        price_rub = int(val2)
        product_desc = f"{stars} ⭐ Звёзд Telegram"
        await state.update_data(category="stars", amount=stars, price_rub=price_rub, product_desc=product_desc)
        text = f"<b>Вы выбрали:</b>\n{product_desc}\n💰 Цена: <b>{price_rub} ₽</b>\n\nВведите ваш Telegram никнейм:"
    else:
        months = int(val1)
        price_rub = int(val2)
        product_desc = f"{months} месяцев Telegram Premium"
        await state.update_data(category="premium", amount=months, price_rub=price_rub, product_desc=product_desc)
        text = f"<b>Вы выбрали:</b>\n{product_desc}\n💰 Цена: <b>{price_rub} ₽</b>\n\nВведите ваш Telegram никнейм:"

    await callback.message.edit_text(text)
    await state.set_state(OrderStates.waiting_username)
    await callback.answer()


@dp.callback_query(F.data == "stars:custom")
async def callback_custom_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"✨ Введите количество звёзд (минимум 10):\nЦена за 1 звезду: {STAR_PRICE_PER_UNIT} ₽")
    await state.set_state(OrderStates.waiting_amount)
    await callback.answer()


@dp.message(StateFilter(OrderStates.waiting_amount))
async def process_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("category")

    if category == "stars":
        try:
            amount = int(message.text.strip())
            if amount < 10:
                await message.answer("❗ Минимум 10 звёзд")
                return
            price_rub = round(amount * STAR_PRICE_PER_UNIT)
            product_desc = f"{amount} ⭐ Звёзд Telegram"
            await state.update_data(amount=amount, price_rub=price_rub, product_desc=product_desc)
            await message.answer(
                f"<b>Вы выбрали:</b>\n{product_desc}\n💰 Цена: <b>{price_rub} ₽</b>\n\nВведите ваш Telegram никнейм:")
            await state.set_state(OrderStates.waiting_username)
        except ValueError:
            await message.answer("❗ Введите целое число")

    elif category == "ton":
        try:
            amount = float(message.text.replace(",", "."))
            if amount < 0.1:
                await message.answer("❗ Минимальная сумма — 0.1 TON")
                return
            price_usdt = round(amount * TON_PRICE, 4)
            product_desc = f"{amount} TON"
            await state.update_data(amount=amount, price_usdt=price_usdt, product_desc=product_desc)
            await message.answer(
                f"<b>Вы выбрали:</b>\n{product_desc}\n💰 Цена: <b>{price_usdt} USDT</b>\n\nВведите ваш TON-кошелёк:")
            await state.set_state(OrderStates.waiting_username)
        except ValueError:
            await message.answer("❗ Введите число (например: 1.5 или 5)")
    else:
        await message.answer("❌ Неизвестная категория. Начните заново /start")


@dp.message(StateFilter(OrderStates.waiting_username))
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    data = await state.get_data()
    category = data["category"]
    product_desc = data["product_desc"]

    if category == "ton":
        price_display = f"<b>{data['price_usdt'] * get_usdt_rate_coingecko():.0f} ₽</b>"
    else:
        price_display = f"<b>{data['price_rub']} ₽</b>"

    confirm_text = f"""<b>Подтверждение заказа</b>
🛒 Товар: {product_desc}
💰 Цена: {price_display}
👤 Никнейм/кошелёк: {username}

Выберите способ оплаты:"""

    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Оплатить криптой (USDT)", callback_data="confirm_pay:crypto")
    builder.button(text="💳 Оплатить по номеру", callback_data="confirm_pay:manual")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)

    await message.answer(confirm_text, reply_markup=builder.as_markup())
    await state.update_data(username=username)
    await state.set_state(OrderStates.waiting_payment)


@dp.callback_query(F.data == "confirm_pay:crypto")
async def callback_confirm_pay_crypto(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_desc = data["product_desc"]
    username = data["username"]
    category = data.get("category")

    if category == "ton":
        amount_usdt = data["price_usdt"]
        price_rub = None
        kurs_text = ""
    else:
        price_rub = data["price_rub"]
        rate = get_usdt_rate_coingecko()
        amount_usdt = round(price_rub / rate, 4)
        kurs_text = f"Курс: 1 USDT ≈ {round(rate, 2)} ₽\n≈ {price_rub} ₽\n\n"

    description = f"Заказ {product_desc} | Ник: {username} | ID: {callback.from_user.id}"
    invoice_response = create_cryptobot_invoice(amount_usdt, description)

    if not invoice_response.get("ok"):
        await callback.message.edit_text("❌ Ошибка создания счёта. Попробуйте позже.")
        await state.clear()
        return

    result = invoice_response["result"]
    invoice_id = result["invoice_id"]
    bot_invoice_url = result["bot_invoice_url"]

    await state.update_data(invoice_id=invoice_id, payment_type="crypto",
                            amount_usdt=amount_usdt, price_rub=price_rub)

    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Оплатить USDT", url=bot_invoice_url)
    builder.button(text="🔄 Проверить оплату", callback_data="check_payment")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)

    await callback.message.edit_text(
        f"<b>✅ Счёт создан!</b>\n\n"
        f"💰 Сумма: <b>{amount_usdt} USDT</b>\n"
        f"{kurs_text}"
        f"Оплатите по кнопке ниже и нажмите «Проверить оплату»",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data == "confirm_pay:manual")
async def callback_confirm_pay_manual(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    price_rub = data.get("price_rub") or (get_usdt_rate_coingecko() * data.get("price_usdt", 0))

    product_desc = data["product_desc"]
    username = data["username"]

    await callback.message.edit_text(
        f"""<b>💳 Оплата по номеру телефона</b>\n\n"""
        f"Переведите ровно <b>{price_rub} ₽</b> на Ozon Банк:\n"
        f"<code>{MANUAL_PAYMENT_PHONE}</code>\n\n"
        f"После перевода пришлите сюда скриншот чека.\n\n"
        f"Товар: {product_desc}\nНик/кошелёк: {username}"
    )
    await state.update_data(payment_type="manual")
    await state.set_state(OrderStates.waiting_manual_payment)
    await callback.answer()


@dp.message(StateFilter(OrderStates.waiting_manual_payment), F.photo | F.document)
async def process_manual_payment_proof(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = message.from_user
    user_mention = f"@{user.username}" if user.username else user.full_name

    price_rub = get_usdt_rate_coingecko() * data.get("price_usdt", data.get("price_rub", 0))

    order_text = f"""<b>✅ НОВАЯ ЗАЯВКА (Ручная оплата)</b>
👤 Пользователь: {user_mention} (ID: {message.from_user.id})
🛒 Товар: {data['product_desc']}
👤 Ник/кошелёк: {data['username']}
💰 Сумма: {price_rub} ₽
📱 Способ: Перевод на номер"""

    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=order_text)
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id, caption=order_text)

    await message.answer("✅ Скриншот отправлен администратору!\nОжидайте подтверждения.")
    await state.clear()


@dp.callback_query(F.data == "check_payment")
async def callback_check_payment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    invoice_id = data.get("invoice_id")
    if not invoice_id:
        await callback.answer("Счёт не найден")
        return

    status = get_invoice_status(invoice_id)

    if status == "paid":
        user = callback.from_user
        user_mention = f"@{user.username}" if user.username else user.full_name

        price_rub = data.get('price_rub')
        amount_usdt = data.get('amount_usdt', '—')
        summa_str = f"{price_rub} ₽ (~{amount_usdt} USDT)" if price_rub else f"{amount_usdt} USDT"

        order_text = f"""<b>✅ НОВАЯ ЗАЯВКА (CryptoBot)</b>
👤 Пользователь: {user_mention} (ID: {callback.from_user.id})
🛒 Товар: {data['product_desc']}
👤 Ник/кошелёк: {data['username']}
💰 Сумма: {summa_str}
🧾 Invoice ID: {invoice_id}"""

        await bot.send_message(ADMIN_ID, order_text)
        await callback.message.edit_text("✅ <b>Оплата подтверждена!</b>\nОжидайте выдачи товара.")
        await state.clear()

    elif status == "active":
        await callback.answer("⏳ Оплата ещё не прошла. Попробуйте через 10–15 секунд.")
    else:
        await callback.answer(f"Статус: {status}. Если оплатили — напишите админу.")

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
