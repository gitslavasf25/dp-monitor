"""
ДП Документ Вроцлав — монитор свободных слотов
С residential proxy (WebShare, Germany)
Активен: 07:00 - 01:00 по Варшаве
Интервал: 10 минут
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
CHECK_INTERVAL     = 600  # 10 минут

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
