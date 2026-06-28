import os
import requests
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
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
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

    price = data["market_data"]["current_price"]["usd"]
    change = data["market_data"]["price_change_percentage_24h"]

    return float(price), float(change)


def build_report():

    price, change = get_btc_price()

    today = datetime.now(
        ZoneInfo("Asia/Bangkok")
    ).strftime("%d/%m/%Y")

    message = f"""₿ Bitcoin Daily Report (STEP 1)

ประจำวันที่ {today}

━━━━━━━━━━━━━━

Bitcoin Price
${price:,.2f}

24h Change
{change:+.2f}%

Data Source
✅ CoinGecko API

Status
✅ API Connected
"""

    return message


if __name__ == "__main__":

    report = build_report()

    print(report)

    send_line_message(report)
