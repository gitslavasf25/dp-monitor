"""
ДП Документ Вроцлав — облачный монитор свободных слотов
Логика: если страница загрузилась и НЕТ фразы "всі місця зайняті" — значит места есть.
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── Конфиг ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL         = "https://wroclaw.pasport.org.ua/solutions/e-queue"

CHECK_ROUNDS  = int(os.environ.get("CHECK_ROUNDS", "1"))
SLEEP_BETWEEN = int(os.environ.get("SLEEP_BETWEEN", "0"))

EXPIRY_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ   = timezone(timedelta(hours=2))  # CEST летнее время

# ── Фразы которые сайт показывает когда мест НЕТ ─────────────────────────────
NO_SLOTS_PHRASES = [
    "всі місця зайняті",
    "кількість талонів обмежена",
    "спробуйте в інший час",
    "немає вільних",
    "запис недоступний",
    "немає доступних",
    "вільних місць немає",
    "сервіс не доступний",
]

# ── Фразы которые говорят что страница вообще не загрузилась ─────────────────
PAGE_ERROR_PHRASES = [
    "service is not available",
    "404",
    "error",
    "щось пішло не так",
]

# ── Проверка временного окна (06:00–02:00 по Варшаве) ────────────────────────
def is_active_hours() -> bool:
    hour = datetime.now(WARSAW_TZ).hour
    return not (2 <= hour < 6)

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("[Telegram] ✅ Сообщение отправлено")
    except Exception as e:
        print(f"[Telegram ERROR] {e}")

# ── Проверка сайта ────────────────────────────────────────────────────────────
def check_slots() -> tuple[bool, str]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="uk-UA",
            viewport={"width": 1280, "height": 800},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()

        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=45_000)
        except Exception as e:
            browser.close()
            return None, f"Ошибка загрузки страницы: {e}"

        # Ждём пока JS полностью отрисует контент
        page.wait_for_timeout(5000)
        content = page.content().lower()
        page.screenshot(path="screenshot.png", full_page=True)
        browser.close()

        # Проверяем что страница вообще загрузилась нормально
        # Страница должна содержать хоть что-то специфичное для сайта
        if "pasport" not in content and "документ" not in content:
            return None, "Страница загрузилась некорректно — нет признаков сайта"

        # Проверяем ошибки сервиса
        for phrase in PAGE_ERROR_PHRASES:
            if phrase in content and "pasport" not in content:
                return None, f"Ошибка сервиса: «{phrase}»"

        # Главная логика: ищем фразу "мест нет"
        for phrase in NO_SLOTS_PHRASES:
            if phrase in content:
                return False, f"Мест нет (фраза: «{phrase}»)"

        # Фраза "мест нет" НЕ найдена — значит страница открылась в рабочем режиме
        # и показывает форму записи / календарь
        return True, "Фраза 'всі місця зайняті' не найдена — вероятно доступна запись!"

# ── Основная логика ───────────────────────────────────────────────────────────
def main():
    now_utc    = datetime.now(timezone.utc)
    now_warsaw = datetime.now(WARSAW_TZ)

    print(f"Время UTC:     {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Время Варшава: {now_warsaw.strftime('%Y-%m-%d %H:%M:%S')}")

    if now_utc >= EXPIRY_DATE:
        print("⏹ Мониторинг завершён — истёк срок (01.06.2026).")
        sys.exit(0)

    if not is_active_hours():
        print("😴 Вне рабочего окна (02:00–06:00 по Варшаве). Пропускаем.")
        sys.exit(0)

    print(f"🔍 Запуск {CHECK_ROUNDS} проверок, пауза {SLEEP_BETWEEN} сек.\n")

    for i in range(1, CHECK_ROUNDS + 1):
        ts = datetime.now(WARSAW_TZ).strftime("%H:%M:%S")
        print(f"[{ts}] Проверка {i}/{CHECK_ROUNDS}...", end=" ", flush=True)

        found, details = check_slots()

        if found is None:
            # Страница не загрузилась — пропускаем эту итерацию
            print(f"⚠️ {details}")
        elif found:
            print(f"✅ ЕСТЬ МЕСТА! {details}")
            now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M по Варшаве")
            msg = (
                f"🟢 <b>ЕСТЬ СВОБОДНЫЕ МЕСТА!</b>\n\n"
                f"📍 ДП Документ Вроцлав\n"
                f"🕐 {now_str}\n\n"
                f"👉 <a href='{TARGET_URL}'>Записаться сейчас!</a>"
            )
            send_telegram(msg)
            sys.exit(0)
        else:
            print(f"⏳ {details}")

        if i < CHECK_ROUNDS and SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)

    print("\nВсе проверки завершены. Свободных мест не найдено.")

if __name__ == "__main__":
    main()
