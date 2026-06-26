import os
import requests

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

    print("LINE status:", response.status_code)
    print(response.text)

    response.raise_for_status()


send_line_message("✅ Bitcoin Daily Report test สำเร็จ")
