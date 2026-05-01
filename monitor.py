"""
ДП Документ Вроцлав — монитор свободных слотов
Логика:
1. Если Cloudflare блокировка — пропускаем
2. Если НЕТ "всі місця зайняті" на реальной странице — есть слоты
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
CHECK_INTERVAL     = 60  # секунд между проверками

NEGATIVE_PHRASE    = "всі місця зайняті"

# Признаки что страница НЕ загрузилась (Cloudflare / ошибка)
BLOCK_PHRASES = [
    "security verification",
    "security service to protect",
    "cloudflare",
    "checking your browser",
    "please wait",
    "enable javascript",
    "ray id:",
]

# ─────────────────────────────────────────────
def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except:
        pass

# ─────────────────────────────────────────────
def check_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()
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

    # Проверяем что не Cloudflare блокировка
    for phrase in BLOCK_PHRASES:
        if phrase in text:
            return None, f"Cloudflare блокировка (признак: «{phrase}»)"

    # Проверяем что страница вообще содержит что-то от сайта
    if "pasport" not in text and "документ" not in text and "місця" not in text:
        return None, "Страница загрузилась некорректно — нет признаков сайта"

    # Основная логика
    if NEGATIVE_PHRASE in text:
        return False, "Найдена фраза: мест нет"
    else:
        return True, "Фраза 'всі місця зайняті' НЕ найдена — возможна запись!"

# ─────────────────────────────────────────────
def is_active_hours():
    hour = datetime.now(WARSAW_TZ).hour
    return not (2 <= hour < 6)

# ─────────────────────────────────────────────
def main():
    print("🚀 Монитор запущен, интервал:", CHECK_INTERVAL, "сек.")

    while True:
        if datetime.now(timezone.utc) >= EXPIRY_DATE:
            print("⏹ Срок истёк.")
            sys.exit(0)

        if not is_active_hours():
            print(f"😴 Вне рабочего окна, спим 5 мин...")
            time.sleep(300)
            continue

        now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M")
        ts = datetime.now(WARSAW_TZ).strftime("%H:%M:%S")
        print(f"[{ts}] Проверка...", end=" ", flush=True)

        result, msg = check_page()

        if result is None:
            print(f"⚠️ {msg}")
        elif result:
            print(f"✅ ЕСТЬ СЛОТЫ! {msg}")
            send_telegram(
                f"🟢 <b>ВОЗМОЖНО ЕСТЬ СЛОТЫ!</b>\n\n"
                f"📍 ДП Документ Вроцлав\n"
                f"🕐 {now_str}\n\n"
                f"👉 <a href='{TARGET_URL}'>Открыть сайт</a>"
            )
            time.sleep(600)  # после алерта ждём 10 мин
        else:
            print(f"⏳ {msg}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
