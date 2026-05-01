"""
ДП Документ Вроцлав — облачный монитор свободных слотов
Запускается через GitHub Actions каждые 5 минут.
Внутри одного запуска делает 6 проверок с паузой ~50 сек.
При нахождении свободных мест — отправляет Telegram уведомление.
Активен: до 01.06.2026, время: 06:00–02:00 по Варшаве.
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── Конфиг ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ЗАМЕНИ_НА_ТОКЕН")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "1737942735")
TARGET_URL         = "https://wroclaw.pasport.org.ua/solutions/e-queue"

CHECK_ROUNDS  = int(os.environ.get("CHECK_ROUNDS", "1"))
SLEEP_BETWEEN = int(os.environ.get("SLEEP_BETWEEN", "0"))

EXPIRY_DATE   = datetime(2026, 6, 1, tzinfo=timezone.utc)
WARSAW_TZ     = timezone(timedelta(hours=2))  # CEST (летнее время)

# ── Проверка временного окна (06:00–02:00 по Варшаве) ────────────────────────
def is_active_hours() -> bool:
    """
    Активные часы: 06:00–23:59 и 00:00–01:59 по Варшаве.
    То есть НЕ активен только с 02:00 до 05:59.
    """
    now_warsaw = datetime.now(WARSAW_TZ)
    hour = now_warsaw.hour
    # Неактивный период: 02:00–05:59
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
            return False, f"Ошибка загрузки страницы: {e}"

        # Ждём пока JS полностью отрисует контент
        page.wait_for_timeout(5000)
        content = page.content().lower()

        # ── 1. Негативные сигналы — мест точно нет ──
        negatives = [
            "немає вільних",
            "нет свободных",
            "сервіс не доступний",
            "сервис не доступен",
            "service is not available",
            "запис недоступний",
            "немає доступних",
            "вільних місць немає",
        ]
        for neg in negatives:
            if neg in content:
                page.screenshot(path="screenshot.png", full_page=True)
                browser.close()
                return False, f"Нет мест (фраза: «{neg}»)"

        # ── 2. Активные ячейки календаря/слотов ──
        slot_selectors = [
            ".day:not(.disabled):not(.past):not(.off)",
            "td.available",
            "td.active:not(.disabled)",
            "[class*='slot']:not([class*='disabled']):not([class*='booked'])",
            "[class*='available']:not([class*='un'])",
            "button.slot:not([disabled])",
            "[data-date]:not(.disabled)",
        ]
        for sel in slot_selectors:
            try:
                els = page.query_selector_all(sel)
                if els:
                    count = len(els)
                    page.screenshot(path="screenshot.png", full_page=True)
                    browser.close()
                    return True, f"Найдено доступных слотов: {count} (селектор: {sel})"
            except Exception:
                continue

        # ── 3. Активные кнопки записи ──
        positive_phrases = [
            "вибрати дату",
            "обрати дату",
            "оформити документ",
            "записатись",
            "обрати час",
            "вибрати час",
            "підібрати час",
        ]
        for el in page.query_selector_all("button:not([disabled]), [role='button']:not([disabled])"):
            try:
                t = el.inner_text().strip().lower()
                for phrase in positive_phrases:
                    if phrase in t:
                        page.screenshot(path="screenshot.png", full_page=True)
                        browser.close()
                        return True, f"Активная кнопка записи: «{t[:80]}»"
            except Exception:
                continue

        # ── 4. Select/dropdown с доступными датами ──
        try:
            options = page.query_selector_all("select option:not([disabled]):not([value=''])")
            if len(options) > 0:
                page.screenshot(path="screenshot.png", full_page=True)
                browser.close()
                return True, f"Доступных дат в выпадающем списке: {len(options)}"
        except Exception:
            pass

        page.screenshot(path="screenshot.png", full_page=True)
        browser.close()
        return False, "Свободных слотов не обнаружено"

# ── Основная логика ───────────────────────────────────────────────────────────
def main():
    now_utc = datetime.now(timezone.utc)
    now_warsaw = datetime.now(WARSAW_TZ)

    print(f"Время UTC:    {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Время Варшава: {now_warsaw.strftime('%Y-%m-%d %H:%M:%S')}")

    # Проверка срока действия
    if now_utc >= EXPIRY_DATE:
        print("⏹ Мониторинг завершён — истёк срок (01.06.2026).")
        sys.exit(0)

    # Проверка временного окна
    if not is_active_hours():
        print(f"😴 Вне рабочего окна (02:00–06:00 по Варшаве). Пропускаем.")
        sys.exit(0)

    print(f"🔍 Запуск {CHECK_ROUNDS} проверок, пауза {SLEEP_BETWEEN} сек.\n")
    send_telegram("🧪 Тест: бот работает! Мониторинг ДП Документ Вроцлав активен.")
    sys.exit(0)

    for i in range(1, CHECK_ROUNDS + 1):
        ts = datetime.now(WARSAW_TZ).strftime("%H:%M:%S")
        print(f"[{ts}] Проверка {i}/{CHECK_ROUNDS}...", end=" ", flush=True)
        

        found, details = check_slots()

        if found:
            print(f"✅ ЕСТЬ МЕСТА! {details}")
            now_str = datetime.now(WARSAW_TZ).strftime("%d.%m.%Y %H:%M по Варшаве")
            msg = (
                f"🟢 <b>ЕСТЬ СВОБОДНЫЕ МЕСТА!</b>\n\n"
                f"📍 ДП Документ Вроцлав\n"
                f"🕐 {now_str}\n"
                f"ℹ️ {details}\n\n"
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
