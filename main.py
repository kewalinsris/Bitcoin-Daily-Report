import os
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]


def send_line_message(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }

    response = requests.post(url, headers=headers, json=payload)
    print(response.status_code)
    print(response.text)
    response.raise_for_status()


def get_btc_price():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"

    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false"
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    return (
        float(data["market_data"]["current_price"]["usd"]),
        float(data["market_data"]["price_change_percentage_24h"])
    )
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(
        data,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ],
    )

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])

    return df


def build_report():
    df = get_binance_btc_ohlcv()

    latest = float(df["close"].iloc[-1])
    previous = float(df["close"].iloc[-2])
    change_pct = (latest - previous) / previous * 100

    date_th = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y")

    message = f"""₿ Bitcoin Daily Report Test
ประจำวันที่ {date_th}

━━━━━━━━━━━━━━

Bitcoin
${latest:,.2f} ({change_pct:+.2f}%)

Data Source
✅ Binance BTCUSDT Daily OHLCV

System Status
✅ Binance Connected
✅ LINE Connected
"""

    return message


if __name__ == "__main__":
    report = build_report()
    print(report)
    send_line_message(report)
