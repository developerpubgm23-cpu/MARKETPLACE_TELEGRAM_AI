"""
Telegram userbot: incoming private Telegram messages -> Groq AI -> Telegram reply.

Install:
  python -m pip install --no-cache-dir telethon python-dotenv requests

Run:
  python bot.py

.env kerak:
  TELEGRAM_API_ID=123456
  TELEGRAM_API_HASH=your_telegram_api_hash
  TELEGRAM_SESSION=groq_session
  GROQ_API_KEY=gsk_...
  GROQ_MODEL=llama-3.3-70b-versatile

Muhim:
  GROQ_API_URL yozmasangiz ham bo'ladi. To'g'ri URL avtomatik ishlatiladi:
  https://api.groq.com/openai/v1/chat/completions
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from telethon import TelegramClient, events

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "groq_session").strip() or "groq_session"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
GROQ_API_URL = (
    os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
    or "https://api.groq.com/openai/v1/chat/completions"
)

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant. Reply clearly and briefly in the user's language.",
)
MAX_TELEGRAM_LENGTH = 3900
REQUEST_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "60"))


def fail_if_missing_env() -> None:
    missing = []
    if not TELEGRAM_API_ID:
        missing.append("TELEGRAM_API_ID")
    if not TELEGRAM_API_HASH:
        missing.append("TELEGRAM_API_HASH")
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")

    if missing:
        print(".env ichida quyidagilar yetishmayapti: " + ", ".join(missing))
        raise SystemExit(1)

    if not TELEGRAM_API_ID.isdigit():
        print("TELEGRAM_API_ID faqat raqam bo'lishi kerak.")
        raise SystemExit(1)

    if "console.groq.com" in GROQ_API_URL:
        print("XATO: GROQ_API_URL console.groq.com bo'lmasligi kerak.")
        print("To'g'ri URL: https://api.groq.com/openai/v1/chat/completions")
        raise SystemExit(1)

    if not GROQ_API_URL.endswith("/chat/completions"):
        print("XATO: GROQ_API_URL noto'g'ri.")
        print("To'g'ri URL: https://api.groq.com/openai/v1/chat/completions")
        raise SystemExit(1)


def extract_groq_text(data: Dict[str, Any]) -> Optional[str]:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def query_groq(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return f"Groq bilan ulanishda xato: {exc}"

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.status_code == 401:
        return "Groq API key noto'g'ri yoki eskirgan. console.groq.com/keys dan yangi key oling."

    if response.status_code == 404:
        return (
            "Groq URL noto'g'ri. .env ichida shunday bo'lsin:\n"
            "GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions"
        )

    if not response.ok:
        return f"Groq API xatosi [{response.status_code}]: {json.dumps(data, ensure_ascii=False)[:1200]}"

    answer = extract_groq_text(data)
    if not answer:
        return f"Groq javob formatini o'qib bo'lmadi: {json.dumps(data, ensure_ascii=False)[:1200]}"

    return answer.strip()


def split_for_telegram(text: str, limit: int = MAX_TELEGRAM_LENGTH):
    text = text or "AI bo'sh javob qaytardi."
    for start in range(0, len(text), limit):
        yield text[start : start + limit]


fail_if_missing_env()
telegram_client = TelegramClient(TELEGRAM_SESSION, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)


@telegram_client.on(events.NewMessage(incoming=True))
async def handler(event):
    if not event.is_private:
        return

    text = (event.raw_text or "").strip()
    if not text:
        return

    if text.lower() in {"/start", "/help"}:
        await event.reply("Salom. Xabar yuboring, men uni Groq AI ga yuborib javob qaytaraman.")
        return

    sender = await event.get_sender()
    sender_name = getattr(sender, "username", None) or getattr(sender, "first_name", None) or str(getattr(sender, "id", "unknown"))
    print(f"Telegramdan xabar: {sender_name}: {text[:120]}")

    await event.reply("⏳")
    loop = asyncio.get_running_loop()
    ai_response = await loop.run_in_executor(None, query_groq, text)

    for part in split_for_telegram(ai_response):
        await event.reply(part)


def main() -> None:
    print("Telegram client ishga tushmoqda...")
    print(f"Groq model: {GROQ_MODEL}")
    print(f"Groq URL: {GROQ_API_URL}")
    telegram_client.start()
    print("Client tayyor. Private xabarlarni kutyapti...")
    telegram_client.run_until_disconnected()


if __name__ == "__main__":
    main()
