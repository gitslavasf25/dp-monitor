"""
ДП Документ Вроцлав — монитор свободных слотов
С residential proxy (WebShare, Germany)
10:00-18:00 по Варшаве - проверка каждые 10 минут
Остальное время - каждые 5 минут
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL         = "https://wroclaw.pasport.org.ua/solutions/e-queue"
EXPIRY_DATE        = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ          = timezone(timedelta(hours=2))

NEGATIVE_PHRASE = "всі місця зайняті"
BLOCK_PHRASES = [
    "security verification",
    "security service to protect",
    "cloudflare",
    "checking your browser",
    "ray id:",
]

PROXY = {
    "server":   "http://p.webshare.io:80",
    "username": "dohwemux-de-3",
    "password": "oinseleltx69",
}

def get_interval():
    hour = datetime.now(WARSAW_TZ).hour
    if 10 <= hour < 18:
        return 600
    return 300

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except:
        pass

def check_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=PROXY,
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="uk-UA",
        )
        page = ctx.new_page()
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as e:
            browser.close()
            return None, f"Ошибка загрузки: {e}"

        text = page.inner_text("body").lower()
        text = " ".join(text.split())
        browser.close()

    print("DEBUG TEXT:", text[:300])

    for phrase in BLOCK_PHRASES:
        if phrase in text:
            return None, f"Заблокировано: {phrase}"

    if "pasport" not in text and "місця" not in text and "документ" not in text:
        return None, "Страница загрузилась некорректно"

    if NEGATIVE_PHRASE in text:
        return False, "Мест нет"
    else:
        return True, "Фраза не найдена - возможна запись!"

def is_active_hours():
    hour = datetime.now(WARSAW_TZ).hour
    return not (2 <= hour < 6)

def main():
    print("Монитор запущен с proxy Germany")
    print("10:00-18:00 каждые 10 мин, остальное время каждые 5 мин")

    while True:
        if datetime.now(timezone.utc) >= EXPIRY_DATE:
            print("Срок истёк.")
            sys.exit(0)

        if not is_active_hours():
            print("Вне рабочего окна 02:00-06:00, спим 5 мин...")
            time.sleep(300)
            continue

        interval = get_interval()
        ts = datetime.now(WARSAW_TZ).strftime("%H:%M:%S")
        mins = interval // 60
        print(f"[{ts}] Проверка, интервал {mins} мин...", end=" ", flush=True)

        result, msg = check_page()

        if result is None:
            print(f"SKIP {msg}")
        elif result:
            print(f"SLOTS FOUND!")
            now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M")
            send_telegram(
                f"🟢 <b>ВОЗМОЖНО ЕСТЬ СЛОТЫ!</b>\n\n"
                f"📍 ДП Документ Вроцлав\n"
                f"🕐 {now_str}\n\n"
                f"👉 <a href='{TARGET_URL}'>Открыть сайт</a>"
            )
            time.sleep(600)
        else:
            print(f"no slots. {msg}")

        time.sleep(interval)

if __name__ == "__main__":
    main()
