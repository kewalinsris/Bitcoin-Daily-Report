import os
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

# Optional hidden MVRV input.
# Add these GitHub Secrets later if you have a usable MVRV API endpoint:
# BGEOMETRICS_API_URL
# BGEOMETRICS_API_KEY
BGEOMETRICS_API_URL = os.environ.get("BGEOMETRICS_API_URL", "").strip()
BGEOMETRICS_API_KEY = os.environ.get("BGEOMETRICS_API_KEY", "").strip()


def send_line_message(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    print("LINE status:", response.status_code)
    print(response.text)
    response.raise_for_status()


def fetch_coingecko_ohlc(days="max"):
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc"
    params = {"vs_currency": "usd", "days": days}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data:
            raise ValueError("CoinGecko OHLC returned empty data")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.date

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = (
            df.dropna(subset=["open", "high", "low", "close"])
            .groupby("date", as_index=False)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .sort_values("date")
            .reset_index(drop=True)
        )
        df["data_quality"] = "CoinGecko OHLC"

        if len(df) < 500:
            raise ValueError(f"Not enough OHLC history: {len(df)} rows")

        return df

    except Exception as e:
        print("OHLC fetch failed. Fallback to market_chart:", str(e))
        return fetch_coingecko_market_chart_fallback(days="max")


def fetch_coingecko_market_chart_fallback(days="max"):
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": days}

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "prices" not in data or not data["prices"]:
        raise ValueError("CoinGecko market_chart returned no price data")

    df = pd.DataFrame(data["prices"], columns=["timestamp", "close"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna(subset=["close"])
        .groupby("date", as_index=False)
        .agg({"close": "last"})
        .sort_values("date")
        .reset_index(drop=True)
    )

    df["open"] = df["close"].shift(1)
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    df["data_quality"] = "CoinGecko market_chart fallback"

    if len(df) < 500:
        raise ValueError(f"Not enough fallback history: {len(df)} rows")

    return df


def fetch_fear_greed():
    url = "https://api.alternative.me/fng/"
    params = {"limit": 1, "format": "json"}

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "data" not in data or not data["data"]:
        raise ValueError("Alternative.me returned no Fear & Greed data")

    item = data["data"][0]
    return int(item["value"]), str(item.get("value_classification", ""))


def parse_numeric_from_json(obj):
    keys = [
        "mvrv_z_score", "mvrv_zscore", "mvrv_z", "mvrvzscore",
        "mvrvZScore", "z_score", "zscore", "value", "v", "y"
    ]

    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                try:
                    return float(obj[key])
                except Exception:
                    pass

        for value in obj.values():
            parsed = parse_numeric_from_json(value)
            if parsed is not None:
                return parsed

    if isinstance(obj, list):
        for item in reversed(obj):
            parsed = parse_numeric_from_json(item)
            if parsed is not None:
                return parsed

    return None


def fetch_mvrv_z_score_optional():
    if not BGEOMETRICS_API_URL:
        return None

    headers = {
        "Accept": "application/json",
        "User-Agent": "Bitcoin-Daily-Report/2.0",
    }

    if BGEOMETRICS_API_KEY:
        headers["Authorization"] = f"Bearer {BGEOMETRICS_API_KEY}"
        headers["X-API-Key"] = BGEOMETRICS_API_KEY

    try:
        response = requests.get(BGEOMETRICS_API_URL, headers=headers, timeout=30)

        if response.status_code >= 400:
            print("MVRV API status:", response.status_code)
            print(response.text[:500])
            return None

        value = parse_numeric_from_json(response.json())
        if value is None:
            print("MVRV API parsed no numeric value")
            return None

        return float(value)

    except Exception as e:
        print("MVRV fetch failed:", str(e))
        return None


def wilder_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def wilder_atr(high, low, close, period=14):
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def calculate_indicators(df):
    df = df.copy()
    close = df["close"]

    df["rsi14"] = wilder_rsi(close, 14)
    df["atr14"] = wilder_atr(df["high"], df["low"], close, 14)
    df["atr_pct"] = df["atr14"] / close * 100
    df["atr_percentile_252"] = df["atr_pct"].rolling(252).rank(pct=True) * 100

    df["sma50"] = close.rolling(50).mean()
    df["sma111"] = close.rolling(111).mean()
    df["sma200"] = close.rolling(200).mean()
    df["sma350x2"] = close.rolling(350).mean() * 2

    df["ath"] = close.cummax()
    df["ath_drawdown_pct"] = (close - df["ath"]) / df["ath"] * 100

    return df


def rsi_status(value):
    if value < 30:
        return "🔵 Oversold"
    if value > 70:
        return "🔴 Overbought"
    return "🟢 Normal"


def fear_status(value):
    if value <= 25:
        return "🔵 Extreme Fear"
    if value <= 45:
        return "🟡 Fear"
    if value <= 55:
        return "🟢 Neutral"
    if value <= 75:
        return "🟡 Greed"
    return "🔴 Extreme Greed"


def trend_status(price, ma, label):
    if price > ma:
        return f"🟢 Above {label}"
    return f"🔴 Below {label}"


def mvrv_zone(mvrv_z):
    if mvrv_z is None:
        return "unknown"
    if mvrv_z < 0.5:
        return "undervalued"
    if mvrv_z < 3:
        return "normal"
    if mvrv_z < 6:
        return "expensive"
    return "overheated"


def get_market_phase(price, ma50, ma200, fear, drawdown, pi_cycle_warning, mvrv_z):
    zone = mvrv_zone(mvrv_z)

    if pi_cycle_warning or zone == "overheated" or (fear >= 80 and zone == "expensive"):
        return "🟡 Distribution"

    if price < ma200 and ma50 < ma200:
        return "🔴 Bear Market"

    if drawdown <= -25 and (fear <= 35 or zone == "undervalued"):
        return "🟢 Accumulation"

    if price > ma200 and ma50 > ma200:
        return "🟢 Bull Market"

    return "🟡 Transition"


def get_dca_status(price, ma200, pi_cycle_warning, mvrv_z):
    zone = mvrv_zone(mvrv_z)

    if pi_cycle_warning or zone == "overheated":
        return "🟡 Continue with Caution"

    if price > ma200:
        return "🟢 Continue"

    if zone == "undervalued":
        return "🟢 Continue / Accumulate"

    return "🟡 Continue with Caution"


def get_buy_the_dip(price, ma200, rsi, fear, drawdown, atr_percentile, mvrv_z):
    total_weight = 0
    score = 0
    reasons = []
    zone = mvrv_zone(mvrv_z)

    # MVRV = 30. If unavailable, normalize score to remaining indicators.
    if zone != "unknown":
        total_weight += 30
        if zone == "undervalued":
            score += 30
            reasons.append("✓ On-chain valuation อยู่ในโซนสะสม")
        elif zone == "normal":
            score += 15
            reasons.append("✓ On-chain valuation ยังไม่แพงเกินไป")

    # ATH Drawdown = 25
    total_weight += 25
    if drawdown <= -35:
        score += 25
        reasons.append("✓ ราคาย่อลึกมากจาก ATH")
    elif drawdown <= -25:
        score += 20
        reasons.append("✓ ราคาย่อลงมากกว่า 25% จาก ATH")
    elif drawdown <= -15:
        score += 12
        reasons.append("✓ ราคาย่อลงมากกว่า 15% จาก ATH")

    # RSI = 15
    total_weight += 15
    if rsi < 30:
        score += 15
        reasons.append("✓ RSI อยู่ในโซน Oversold")
    elif rsi < 40:
        score += 8
        reasons.append("✓ RSI เริ่มอ่อนตัว")

    # Fear & Greed = 15
    total_weight += 15
    if fear <= 25:
        score += 15
        reasons.append("✓ ตลาดอยู่ใน Extreme Fear")
    elif fear <= 40:
        score += 8
        reasons.append("✓ ตลาดอยู่ในโซน Fear")

    # ATR = 10
    total_weight += 10
    if atr_percentile < 80:
        score += 10
        reasons.append("✓ ความผันผวนยังไม่สูงผิดปกติ")
    elif atr_percentile < 90:
        score += 5
        reasons.append("✓ ความผันผวนสูง แต่ยังไม่สุดโต่ง")

    # Trend = 5
    total_weight += 5
    if price > ma200:
        score += 5
        reasons.append("✓ ราคาอยู่เหนือ 200 DMA")

    normalized = round(score / total_weight * 100)

    if normalized >= 75:
        text = f"🔵 YES ({normalized}%)"
        if reasons:
            text += "\n\nเหตุผล\n" + "\n".join(reasons[:5])
        return text

    if normalized >= 60:
        text = f"🟡 Watchlist ({normalized}%)"
        if reasons:
            text += "\n\nเหตุผล\n" + "\n".join(reasons[:5])
        return text

    return f"❌ Not Yet ({normalized}%)"


def get_profit_strategy(rsi, fear, drawdown, pi_cycle_warning, mvrv_z):
    zone = mvrv_zone(mvrv_z)
    signals = []
    hard_confirmation = False

    if zone == "overheated":
        signals.append("✓ On-chain valuation อยู่ในโซนร้อนแรงมาก")
        hard_confirmation = True
    elif zone == "expensive":
        signals.append("✓ On-chain valuation เริ่มแพง")

    if pi_cycle_warning:
        signals.append("✓ Pi Cycle ส่งสัญญาณเตือน")
        hard_confirmation = True

    if rsi > 80:
        signals.append("✓ RSI สูงกว่า 80")
    elif rsi > 70:
        signals.append("✓ RSI สูงกว่า 70")

    if fear >= 90:
        signals.append("✓ Fear & Greed อยู่ใน Extreme Greed")
    elif fear >= 80:
        signals.append("✓ Fear & Greed สูงมาก")

    if drawdown > -3:
        signals.append("✓ ราคาอยู่ใกล้ ATH")

    if hard_confirmation and len(signals) >= 3:
        text = "🔴 Strong Profit Taking"
        text += "\n\nเหตุผล\n" + "\n".join(signals[:5])
        return text

    if len(signals) >= 3:
        text = "🟡 Gradual Profit Taking"
        text += "\n\nเหตุผล\n" + "\n".join(signals[:5])
        return text

    if hard_confirmation and len(signals) >= 2:
        text = "🟡 Gradual Profit Taking"
        text += "\n\nเหตุผล\n" + "\n".join(signals[:5])
        return text

    return "❌ Hold"


def build_report():
    df = fetch_coingecko_ohlc(days="max")
    df = calculate_indicators(df)

    clean = df.dropna(
        subset=[
            "close",
            "rsi14",
            "sma50",
            "sma111",
            "sma200",
            "sma350x2",
            "ath_drawdown_pct",
            "atr_percentile_252",
        ]
    ).copy()

    if len(clean) < 2:
        raise ValueError("Not enough clean indicator data")

    latest = clean.iloc[-1]
    previous = clean.iloc[-2]

    price = float(latest["close"])
    previous_price = float(previous["close"])
    change_pct = (price - previous_price) / previous_price * 100

    rsi = float(latest["rsi14"])
    ma50 = float(latest["sma50"])
    ma200 = float(latest["sma200"])
    ma111 = float(latest["sma111"])
    ma350x2 = float(latest["sma350x2"])

    drawdown = float(latest["ath_drawdown_pct"])
    atr_percentile = float(latest["atr_percentile_252"])

    pi_cycle_warning = ma111 >= ma350x2

    fear, _fear_label = fetch_fear_greed()
    mvrv_z = fetch_mvrv_z_score_optional()

    phase = get_market_phase(
        price=price,
        ma50=ma50,
        ma200=ma200,
        fear=fear,
        drawdown=drawdown,
        pi_cycle_warning=pi_cycle_warning,
        mvrv_z=mvrv_z,
    )

    dca = get_dca_status(
        price=price,
        ma200=ma200,
        pi_cycle_warning=pi_cycle_warning,
        mvrv_z=mvrv_z,
    )

    buy_dip = get_buy_the_dip(
        price=price,
        ma200=ma200,
        rsi=rsi,
        fear=fear,
        drawdown=drawdown,
        atr_percentile=atr_percentile,
        mvrv_z=mvrv_z,
    )

    profit = get_profit_strategy(
        rsi=rsi,
        fear=fear,
        drawdown=drawdown,
        pi_cycle_warning=pi_cycle_warning,
        mvrv_z=mvrv_z,
    )

    trend_50 = trend_status(price, ma50, "50 DMA")
    trend_200 = trend_status(price, ma200, "200 DMA")

    date_th = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y")

    message = f'''₿ Bitcoin Daily Report
ประจำวันที่ {date_th}

━━━━━━━━━━━━━━

Bitcoin Price
${price:,.0f} ({change_pct:+.2f}%)

Market Phase
{phase}

RSI (14)
{rsi_status(rsi)} ({rsi:.1f})

Fear & Greed
{fear_status(fear)} ({fear})

Trend
{trend_50}
{trend_200}

ATH Drawdown
{drawdown:.1f}%

━━━━━━━━━━━━━━

DCA
{dca}

Buy the Dip
{buy_dip}

Profit Strategy
{profit}
'''

    print("Data source:", latest.get("data_quality", "unknown"))
    print("MVRV available:", mvrv_z is not None)

    return message


if __name__ == "__main__":
    report = build_report()
    print(report)
    send_line_message(report)
