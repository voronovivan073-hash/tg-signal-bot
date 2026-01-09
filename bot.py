import os
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ========= НАСТРОЙКИ =========

TOKEN = os.getenv("TOKEN") or "ВСТАВЬ_СЮДА_ТОКЕН"

PAIRS = {
    "EURUSDT": "EUR/USD",
    "GBPUSDT": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSDT": "AUD/USD"
}

TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m"
}

EMA_FAST = 9
EMA_SLOW = 21

AUTO_USERS = set()
USER_STATE = {}   # user_id -> (pair, timeframe)
LAST_AUTO = set()

# ========= ИНДИКАТОРЫ =========

def get_prices(symbol, tf):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=100"
    data = requests.get(url, timeout=10).json()
    return [float(c[4]) for c in data]

def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values:
        e = v * k + e * (1 - k)
    return e

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    rs = ag / al
    return 100 - (100 / (1 + rs))

def analyze(pair, tf):
    prices = get_prices(pair, tf)
    r = rsi(prices)
    ef = ema(prices, EMA_FAST)
    es = ema(prices, EMA_SLOW)

    trend = "⬆ ВОСХОДЯЩИЙ" if ef > es else "⬇ НИСХОДЯЩИЙ"

    if r < 30 and ef > es:
        signal = "🟢 ПОКУПКА (СИЛЬНЫЙ)"
    elif r > 70 and ef < es:
        signal = "🔴 ПРОДАЖА (СИЛЬНЫЙ)"
    else:
        signal = "⚪ НЕТ СИГНАЛА"

    text = (
        f"📊 {PAIRS[pair]} | TF: {tf}\n\n"
        f"Тренд: {trend}\n"
        f"RSI: {r:.2f}\n"
        f"EMA {EMA_FAST}: {ef:.5f}\n"
        f"EMA {EMA_SLOW}: {es:.5f}\n\n"
        f"Сигнал: {signal}"
    )
    return signal, text

# ========= КНОПКИ =========

def pair_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(name, callback_data=f"pair|{k}")]
        for k, name in PAIRS.items()
    ])

def timeframe_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tf, callback_data=f"tf|{tf}")]
        for tf in TIMEFRAMES
    ])

def main_keyboard(user_id):
    auto = "🔴 Авто-сигналы: ВЫКЛ" if user_id in AUTO_USERS else "🟢 Авто-сигналы: ВКЛ"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить сигнал", callback_data="refresh")],
        [InlineKeyboardButton(auto, callback_data="auto")]
    ])

# ========= HANDLERS =========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери валютную пару:", reply_markup=pair_keyboard())

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    if q.data.startswith("pair|"):
        pair = q.data.split("|")[1]
        USER_STATE[user_id] = [pair, None]
        await q.message.reply_text("Выбери таймфрейм:", reply_markup=timeframe_keyboard())

    elif q.data.startswith("tf|"):
        tf = q.data.split("|")[1]
        USER_STATE[user_id][1] = tf
        pair = USER_STATE[user_id][0]
        _, text = analyze(pair, tf)
        await q.message.reply_text(text, reply_markup=main_keyboard(user_id))

    elif q.data == "refresh":
        if user_id not in USER_STATE or USER_STATE[user_id][1] is None:
            await q.message.reply_text("Сначала выбери пару и таймфрейм.")
            return
        pair, tf = USER_STATE[user_id]
        _, text = analyze(pair, tf)
        await q.message.reply_text(text)

    elif q.data == "auto":
        if user_id in AUTO_USERS:
            AUTO_USERS.remove(user_id)
        else:
            AUTO_USERS.add(user_id)
        await q.message.reply_text("Авто-сигналы переключены.")

# ========= АВТО-СИГНАЛЫ =========

async def auto_loop(app):
    while True:
        await asyncio.sleep(60)
        for user_id in AUTO_USERS:
            for pair in PAIRS:
                for tf in TIMEFRAMES:
                    signal, text = analyze(pair, tf)
                    key = f"{user_id}_{pair}_{tf}"
                    if "СИЛЬНЫЙ" in signal and key not in LAST_AUTO:
                        LAST_AUTO.add(key)
                        await app.bot.send_message(user_id, "🔥 АВТО-СИГНАЛ\n\n" + text)

# ========= MAIN =========

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    asyncio.create_task(auto_loop(app))
    print("Бот запущен")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

