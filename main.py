import os
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]


def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    r = requests.post(url, headers=headers, json=payload)
    print(r.status_code)
    print(r.text)
    r.raise_for_status()


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))


def atr(high, low, close, period=14):
    prev = close.shift(1)
    tr = ((high - low).to_frame("a"))
    tr["b"] = (high - prev).abs()
    tr["c"] = (low - prev).abs()
    return tr.max(axis=1).rolling(period).mean()


def fear_greed():
    url = "https://api.alternative.me/fng/?limit=1"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()["data"][0]
    return int(data["value"]), data["value_classification"]


def status_rsi(x):
    if x < 30:
        return "🔵 Oversold"
    if x > 70:
        return "🔴 Overbought"
    return "🟢 Normal"


def status_fear(x):
    if x <= 25:
        return "🔵 Extreme Fear"
    if x <= 45:
        return "🟡 Fear"
    if x <= 55:
        return "🟢 Neutral"
    if x <= 75:
        return "🟡 Greed"
    return "🔴 Extreme Greed"


def build_report():
    btc = yf.Ticker("BTC-USD").history(period="5y", interval="1d")

    if btc.empty:
        raise ValueError("ไม่สามารถดึงข้อมูล Bitcoin ได้")

    close = btc["Close"].dropna()
    high = btc["High"].dropna()
    low = btc["Low"].dropna()

    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = (price - prev) / prev * 100

    rsi_now = float(rsi(close).dropna().iloc[-1])
    atr_now = float(atr(high, low, close).dropna().iloc[-1])
    atr_pct = atr_now / price * 100

    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    ma111 = float(close.rolling(111).mean().iloc[-1])
    ma350x2 = float(close.rolling(350).mean().iloc[-1] * 2)
    pi_cycle_warning = ma111 >= ma350x2

    ath = float(close.max())
    drawdown = (price - ath) / ath * 100

    fear, fear_label = fear_greed()

    trend50 = "🟢 50 DMA: ขาขึ้น" if price > ma50 else "🔴 50 DMA: ขาลง"
    trend200 = "🟢 200 DMA: ขาขึ้น" if price > ma200 else "🔴 200 DMA: ขาลง"

    # Market Phase
    if pi_cycle_warning or fear >= 80:
        phase = "🟡 Distribution"
    elif price < ma200 and ma50 < ma200:
        phase = "🔴 Bear Market"
    elif fear <= 35 and drawdown <= -25:
        phase = "🟢 Accumulation"
    elif price > ma200 and ma50 > ma200:
        phase = "🟢 Bull Market"
    else:
        phase = "🟡 Transition"

    # DCA
    dca = "🟢 Continue" if price > ma200 and not pi_cycle_warning else "🟡 Review"

    # Buy the Dip weighted score
    score = 0
    reasons = []

    if price > ma200:
        score += 25
        reasons.append("✓ ราคาอยู่เหนือ 200 DMA")
    if fear <= 25:
        score += 15
        reasons.append("✓ Fear & Greed อยู่ใน Extreme Fear")
    if rsi_now < 30:
        score += 15
        reasons.append("✓ RSI อยู่ในภาวะ Oversold")
    if drawdown <= -25:
        score += 25
        reasons.append("✓ ราคาย่อลงมากกว่า 25% จาก ATH")
    elif drawdown <= -15:
        score += 15
        reasons.append("✓ ราคาย่อลงมากกว่า 15% จาก ATH")
    if atr_pct < 8:
        score += 10
        reasons.append("✓ ATR ยังไม่สูงผิดปกติ")
    if price < ma50:
        score += 10
        reasons.append("✓ ราคาย่อต่ำกว่า 50 DMA")

    if score >= 75:
        buy_dip = f"🔵 YES ({score}%)"
        buy_reason = "\n\nเหตุผล\n" + "\n".join(reasons)
    elif score >= 60:
        buy_dip = f"🟡 Watchlist ({score}%)"
        buy_reason = "\n\nเหตุผล\n" + "\n".join(reasons)
    else:
        buy_dip = "❌ Not Yet"
        buy_reason = ""

    # Profit Strategy
    profit_reasons = []
    if pi_cycle_warning:
        profit_reasons.append("✓ Pi Cycle ส่งสัญญาณเตือน")
    if rsi_now > 80:
        profit_reasons.append("✓ RSI สูงกว่า 80")
    if fear >= 90:
        profit_reasons.append("✓ Fear & Greed อยู่ใน Extreme Greed")
    if drawdown > -3:
        profit_reasons.append("✓ ราคาอยู่ใกล้จุดสูงสุด")

    if pi_cycle_warning and len(profit_reasons) >= 3:
        profit = "🔴 Strong Profit Taking"
    elif pi_cycle_warning or len(profit_reasons) >= 3:
        profit = "🟡 Gradual Profit Taking"
    else:
        profit = "❌ Hold"

    profit_reason = ""
    if profit != "❌ Hold":
        profit_reason = "\n\nเหตุผล\n" + "\n".join(profit_reasons)

    date_th = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y")

    return f"""₿ Daily Bitcoin Report
ประจำวันที่ {date_th}

━━━━━━━━━━━━━━

Bitcoin
${price:,.0f} ({change:+.2f}%)

Market Phase
{phase}

RSI (14)
{status_rsi(rsi_now)} ({rsi_now:.1f})

Fear & Greed
{status_fear(fear)} ({fear})

Trend
{trend50}
{trend200}

ระดับราคา
{abs(drawdown):.1f}% ต่ำกว่าจุดสูงสุด (ATH)

━━━━━━━━━━━━━━

DCA
{dca}

Buy the Dip
{buy_dip}{buy_reason}

Profit Strategy
{profit}{profit_reason}
"""


if __name__ == "__main__":
    report = build_report()
    print(report)
    send_line(report)
