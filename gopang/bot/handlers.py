"""
bot/handlers.py — Telegram 봇 메시지 핸들러
고팡 메인 처리 흐름: 수신 → IDDM 분석 → 응답 → PDV 저장
"""
from __future__ import annotations
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import config
from iddm.engine import iddm_engine
from openclaw.client import openclaw
from pdv.vault import pdv
from bot.keyboards import build_warning_keyboard
from models.message import RiskLevel

logger = logging.getLogger(__name__)


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    메시지 수신 → IDDM 분석 → 응답 전송 → PDV 저장
    고팡 7단계 탐지 파이프라인의 진입점
    """
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    message_text = update.message.text

    # 타이핑 표시
    await update.message.chat.send_action(ChatAction.TYPING)

    # ── [단계 0] PDV에서 컨텍스트 로드 ──────────────────────────────
    chat_context = await pdv.load_context(user_id, limit=config.CONTEXT_WINDOW)

    # ── [단계 1~5] IDDM 분석 + OpenClaw 응답 생성 ───────────────────
    analysis, reply = await iddm_engine.analyze(
        user_id=user_id,
        message=message_text,
        context=chat_context,
    )

    # ── [단계 7] Telegram 응답 전송 ──────────────────────────────────
    should_show_buttons = (
        analysis.risk_level.should_offer_block()
        and analysis.confidence >= config.IDDM_BLOCK_THRESHOLD
    )

    if should_show_buttons:
        await update.message.reply_text(
            reply,
            reply_markup=build_warning_keyboard(analysis.risk_level),
        )
    elif analysis.risk_level.should_warn():
        # CR/CV — 경고 포함 응답 (버튼 없음)
        await update.message.reply_text(reply)
    else:
        # 위험 없음 — 일반 응답
        await update.message.reply_text(reply)

    # ── [단계 6] PDV 비동기 저장 ────────────────────────────────────
    asyncio.create_task(
        pdv.save(
            user_id=user_id,
            text=message_text,
            analysis=analysis,
            response=reply,
        )
    )

    logger.info(
        f"[핸들러] 처리 완료 — user={user_id}, "
        f"level={analysis.risk_level.value}, {analysis.processing_ms}ms"
    )


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """인라인 버튼 콜백 처리"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data == "view_pdv":
        history = await pdv.get_history(user_id, limit=10)
        if not history:
            await query.message.reply_text("📭 아직 저장된 대화 기록이 없습니다.")
            return

        lines = ["🔒 **내 PDV 기록** (최근 10개)\n"]
        for h in history:
            risk_emoji = RiskLevel(h["risk_level"]).emoji if h["risk_level"] else "✅"
            text_preview = h["text"][:30] + "..." if len(h["text"]) > 30 else h["text"]
            lines.append(
                f"{risk_emoji} `{h['timestamp'][:16]}` — {text_preview}"
            )
        lines.append(f"\n🔗 체인 ID: `{history[0]['block_hash'][:16]}...`")
        await query.message.reply_text(
            "\n".join(lines), parse_mode="Markdown"
        )

    elif data == "full_analyze":
        await query.message.reply_text(
            "📋 K-Law 상세 분석을 원하시면 분석할 내용을 메시지로 보내주세요.\n"
            "또는 `/analyze [내용]` 명령어를 사용하세요."
        )

    elif data == "cancel_msg":
        await query.message.reply_text(
            "✏️ 메시지 전송을 취소했습니다. 내용을 수정하여 다시 입력해 주세요.\n"
            "도움이 필요하시면 `/help`를 입력하세요."
        )

    elif data == "force_send":
        await query.message.reply_text(
            "⚠️ 전송을 선택하셨습니다.\n"
            "🔒 해당 메시지는 PDV에 기록되었습니다.\n"
            "법적 문제가 발생할 경우 즉시 법률 전문가와 상담하세요."
        )
