"""
DP Dokument Wroclaw - monitor svobodnykh slotov
S residential proxy (WebShare, Germany)
Aktiven: 07:00 - 01:00 po Varshave
Interval: 10 minut - PAUSED (86400)
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL = "https://wroclaw.pasport.org.ua/solutions/e-queue"
EXPIRY_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ = timezone(timedelta(hours=2))
CHECK_INTERVAL = 86400

NEGATIVE_PHRASE = "всі місця зайняті"
BLOCK_PHRASES = [
    "security verification",
    "security service to protect",
    "cloudflare",
    "checking your browser",
    "ray id:",
]

PROXY_SERVER = "http://82.22.232.2:80"
PROXY_USER = "dohwemux-de-3"
PROXY_PASS = "oinseleltx69"


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print("WARNING: TELEGRAM_BOT_TOKEN not set!")
        return
    try:
        r = requests.post(
            "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        print("Telegram response: " + str(r.status_code))
    except Exception as e:
        print("Telegram error: " + str(e))


def check_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy={
                "server": PROXY_SERVER,
                "username": PROXY_USER,
                "password": PROXY_PASS,
            },
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="uk-UA",
        )
        page = ctx.new_page()
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as e:
            browser.close()
            return None, "Load error: " + str(e)

        text = page.inner_text("body").lower()
        text = " ".join(text.split())
        browser.close()

    print("DEBUG: " + text[:300])

    for phrase in BLOCK_PHRASES:
        if phrase in text:
            return None, "Blocked: " + phrase

    if "pasport" not in text and "місця" not in text and "документ" not in text:
        return None, "Page loaded incorrectly"

    if NEGATIVE_PHRASE in text:
        return False, "No slots"
    else:
        return True, "SLOTS AVAILABLE!"


def is_active_hours():
    hour = datetime.now(WARSAW_TZ).hour
    return not (1 <= hour < 7)


def main():
    print("Monitor started. Proxy: Germany. PAUSED mode (86400s interval)")

    while True:
        if datetime.now(timezone.utc) >= EXPIRY_DATE:
            print("Expired.")
            sys.exit(0)

        if not is_active_hours():
            now_str = datetime.now(WARSAW_TZ).strftime("%H:%M")
            print("Inactive hours " + now_str + ", sleeping 10 min...")
            time.sleep(600)
            continue

        ts = datetime.now(WARSAW_TZ).strftime("%H:%M:%S")
        print("[" + ts + "] Checking...", end=" ", flush=True)

        result, msg = check_page()

        if result is None:
            print("SKIP - " + msg)
        elif result:
            print("SLOTS FOUND!")
            now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M")
            send_telegram(
                "SLOTS AVAILABLE - DP Dokument Wroclaw\n"
                + now_str + "\n\n"
                + TARGET_URL
            )
            time.sleep(600)
        else:
            print("No slots")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
