"""
ДП Документ Вроцлав — монитор свободных слотов

Логика:
если на ВИДИМОЙ странице НЕТ "всі місця зайняті"
→ значит возможны свободные слоты
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL         = "https://wroclaw.pasport.org.ua/solutions/e-queue"

EXPIRY_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ   = timezone(timedelta(hours=2))

NEGATIVE_PHRASE = "всі місця зайняті"

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
            return False, f"Ошибка загрузки: {e}"

        # ВАЖНО: берем именно видимый текст страницы
        text = page.inner_text("body").lower()
        text = " ".join(text.split())

        browser.close()

    # debug (очень полезно — оставь пока тестируешь)
    print("DEBUG TEXT:", text[:500])

    # ── Логика ──
    if NEGATIVE_PHRASE in text:
        return False, "Найдена фраза: мест нет"
    else:
        return True, "Фраза НЕ найдена — возможно есть слоты"

# ─────────────────────────────────────────────
def main():
    if datetime.now(timezone.utc) >= EXPIRY_DATE:
        sys.exit(0)

    found, msg = check_page()

    now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M")

    if found:
        print("АЛЕРТ:", msg)

        send_telegram(
            f"🟢 <b>ВОЗМОЖНО ЕСТЬ СЛОТЫ</b>\n\n"
            f"📍 ДП Документ Вроцлав\n"
            f"🕐 {now_str}\n"
            f"ℹ️ {msg}\n\n"
            f"<a href='{TARGET_URL}'>Открыть сайт</a>"
        )
    else:
        print("ОК:", msg)

# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
