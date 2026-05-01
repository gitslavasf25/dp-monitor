"""
ДП Документ Вроцлав — облачный монитор свободных слотов

Логика: если страница загрузилась и НЕТ фразы "всі місця зайняті" — значит места есть.
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── Конфиг ───────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL         = "https://wroclaw.pasport.org.ua/solutions/e-queue"

EXPIRY_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ   = timezone(timedelta(hours=2))

# ── Отсекающие фразы ─────────────────────────
NEGATIVE_PHRASES = [
    "наразі всі місця зайняті",
    "всі місця зайняті",
    "немає вільних місць",
    "наразі всі місця зайняті. будь ласка, спробуйте в інший час або день",
]

# ── Telegram ─────────────────────────────────
def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print("Нет TELEGRAM_BOT_TOKEN")
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
    except Exception as e:
        print("Telegram error:", e)

# ── Проверка страницы ────────────────────────
def check_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        page = browser.new_page()

        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as e:
            browser.close()
            return False, f"Ошибка загрузки: {e}"

        # Получаем и нормализуем HTML
        content = page.content().lower()
        content = " ".join(content.split())

        # debug (можно отключить позже)
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(content)

        browser.close()

    # ── Главная логика ──
    if any(phrase in content for phrase in NEGATIVE_PHRASES):
        return False, "Фраза есть — мест нет"
    else:
        return True, "Фразы нет — возможно есть слоты"

# ── Основная функция ─────────────────────────
def main():
    now_utc = datetime.now(timezone.utc)

    if now_utc >= EXPIRY_DATE:
        print("Срок истёк")
        sys.exit(0)

    found, msg = check_page()

    now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M")

    if found:
        print("АЛЕРТ:", msg)

        send_telegram(
            f"🟢 <b>ВОЗМОЖНО ЕСТЬ СЛОТЫ</b>\n\n"
            f"📍 ДП Документ Вроцлав\n"
            f"🕐 {now_str}\n"
            f"ℹ️ Фраза «всі місця зайняті» НЕ найдена\n\n"
            f"<a href='{TARGET_URL}'>Открыть сайт</a>"
        )
    else:
        print("ОК:", msg)

# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
