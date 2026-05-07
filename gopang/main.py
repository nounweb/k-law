"""
main.py — 고팡 (Gopang) 메인 진입점
FastAPI Webhook 서버 + Telegram Bot

실행:
  python main.py

또는 Polling 모드 (개발용, Webhook 없이):
  python main.py --polling
"""
from __future__ import annotations
import asyncio
import logging
import sys

from fastapi import FastAPI, Request, Response
import uvicorn
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

from config import config
from pdv.vault import pdv
from bot.handlers import handle_message, handle_callback
from bot.commands import cmd_start, cmd_help, cmd_pdv, cmd_verify, cmd_analyze

# ── 로깅 설정 ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gopang")

# ── FastAPI 앱 ───────────────────────────────────────────────────────
app = FastAPI(title="Gopang API", version="1.0.0")

# ── Telegram 봇 애플리케이션 ─────────────────────────────────────────
_bot_app: Application | None = None


def build_application() -> Application:
    """Telegram Bot Application 빌드"""
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # 명령어 핸들러
    application.add_handler(CommandHandler("start",   cmd_start))
    application.add_handler(CommandHandler("help",    cmd_help))
    application.add_handler(CommandHandler("pdv",     cmd_pdv))
    application.add_handler(CommandHandler("verify",  cmd_verify))
    application.add_handler(CommandHandler("analyze", cmd_analyze))

    # 일반 메시지 핸들러 (텍스트만)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # 인라인 버튼 콜백
    application.add_handler(CallbackQueryHandler(handle_callback))

    return application


# ── FastAPI 라이프사이클 ──────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    global _bot_app

    # PDV DB 초기화
    await pdv.initialize()
    logger.info("PDV 초기화 완료")

    # 봇 초기화
    _bot_app = build_application()
    await _bot_app.initialize()

    # Webhook 설정 (WEBHOOK_URL이 있으면)
    if config.WEBHOOK_URL:
        webhook_path = "/gopang/webhook"
        webhook_url = config.WEBHOOK_URL.rstrip("/") + webhook_path
        await _bot_app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook 등록 완료: {webhook_url}")
    else:
        logger.info("WEBHOOK_URL 미설정 — Polling 모드 필요")

    await _bot_app.start()
    logger.info("고팡 봇 시작 완료 🐚")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _bot_app:
        await _bot_app.stop()
        await _bot_app.shutdown()
    logger.info("고팡 봇 종료")


# ── Webhook 엔드포인트 ───────────────────────────────────────────────

@app.post("/gopang/webhook")
async def webhook(request: Request) -> Response:
    """Telegram Webhook 수신"""
    if _bot_app is None:
        return Response(status_code=503)

    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return Response(status_code=200)


@app.get("/health")
async def health() -> dict:
    """헬스체크"""
    return {"status": "ok", "service": "gopang", "version": "1.0.0"}


# ── Polling 모드 (개발용) ────────────────────────────────────────────

async def run_polling() -> None:
    """Webhook 없이 Polling으로 실행 (로컬 개발용)"""
    await pdv.initialize()
    app_bot = build_application()
    logger.info("고팡 Polling 모드 시작 🐚")
    async with app_bot:
        await app_bot.start()
        await app_bot.updater.start_polling(drop_pending_updates=True)
        logger.info("Ctrl+C로 종료하세요...")
        await asyncio.Event().wait()


# ── 진입점 ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    polling_mode = "--polling" in sys.argv

    if polling_mode:
        # 로컬 개발: Polling
        asyncio.run(run_polling())
    else:
        # 프로덕션: Webhook + FastAPI
        uvicorn.run(
            "main:app",
            host=config.SERVER_HOST,
            port=config.SERVER_PORT,
            reload=False,
            log_level="info",
        )
