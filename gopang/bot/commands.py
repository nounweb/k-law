"""
bot/commands.py — 고팡 Telegram 봇 명령어 핸들러
/start, /help, /pdv, /analyze, /verify
"""
from __future__ import annotations
import logging

from telegram import Update
from telegram.ext import ContextTypes

from openclaw.client import openclaw
from pdv.vault import pdv
from bot.keyboards import build_start_keyboard
from models.message import RiskLevel

logger = logging.getLogger(__name__)

# ── /start ──────────────────────────────────────────────────────────

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    /start — 봇 시작 및 K-Law Gopang v1.0 시스템 프롬프트 주입
    매 호출마다 OpenClaw 세션을 초기화하여 방법론을 재주입.
    """
    user = update.effective_user
    user_id = user.id

    # PDV 요약 로드 (이전 대화가 있으면)
    summary = await pdv.load_summary(user_id)

    # ★ K-Law Gopang v1.0 프롬프트 주입 ★
    openclaw.init_session(user_id, context_summary=summary)

    welcome = (
        f"🐚 안녕하세요, {user.first_name}님!\n"
        "저는 **OpenClaw**, 고팡의 AI 법률 비서입니다.\n\n"
        "저는 대화를 실시간으로 분석하여 법적 위험을 미리 알려드립니다:\n\n"
        "🟡 **CR** — 계약 위험 (분쟁 씨앗 감지)\n"
        "🟠 **CV** — 법령 위반 소지 감지\n"
        "🔴 **LB** — 법적 경계 경고\n"
        "🚫 **CC** — 형사 우려 즉시 차단\n\n"
        "📌 **사용법:**\n"
        "• 평소처럼 대화하세요 — 위험 탐지 시 자동 경고\n"
        "• `/analyze [내용]` — K-Law 상세 분석 요청\n"
        "• `/pdv` — 내 대화 기록 (PDV) 조회\n"
        "• `/verify` — PDV 무결성 검증\n"
        "• `/help` — 자세한 도움말\n\n"
        f"🔒 PDV 현황: {summary}\n\n"
        "_K-Law v13.2 + Gopang v1.0 방법론 적용 중_"
    )

    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=build_start_keyboard(),
    )

# ── /help ────────────────────────────────────────────────────────────

async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """도움말"""
    help_text = (
        "📖 **고팡 (Gopang) 사용 안내**\n\n"
        "**기본 사용법**\n"
        "메시지를 보내면 자동으로 위법·분쟁 소지를 분석합니다.\n"
        "위험 탐지 시 등급별 경고 메시지를 받게 됩니다.\n\n"
        "**위험 등급 설명**\n"
        "🟡 CR: 계약·거래 관련 분쟁 씨앗 — 구두 약속, 금전 대여 등\n"
        "🟠 CV: 강행규정 위반 소지 — 이자제한법, 최저임금법 등\n"
        "🔴 LB: 민·형사 책임 직전 단계 — 협박성 표현, 개인정보 침해 등\n"
        "🚫 CC: 형사처벌 가능 표현 — 방화, 폭행, 협박 등\n\n"
        "**명령어 목록**\n"
        "`/start` — 봇 시작 및 K-Law 방법론 재주입\n"
        "`/analyze [내용]` — K-Law 상세 분석 요청\n"
        "`/pdv` — 내 대화 기록 조회 (암호화 저장)\n"
        "`/verify` — PDV 무결성 검증 (OpenHash)\n"
        "`/help` — 이 도움말\n\n"
        "**PDV (Private Data Vault)**\n"
        "모든 대화는 OpenHash 기술로 위변조 불가하게 기록됩니다.\n"
        "오직 본인의 AI 비서만 접근 가능합니다.\n\n"
        "_고팡은 법률 자문을 대체하지 않습니다._\n"
        "_법적 문제 발생 시 전문 변호사와 상담하세요._"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ── /pdv ────────────────────────────────────────────────────────────

async def cmd_pdv(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/pdv — 사용자 대화 기록 조회"""
    user_id = update.effective_user.id
    history = await pdv.get_history(user_id, limit=15)

    if not history:
        await update.message.reply_text(
            "📭 아직 저장된 대화 기록이 없습니다.\n"
            "메시지를 보내면 자동으로 PDV에 저장됩니다."
        )
        return

    # 위험 등급별 통계
    level_count: dict[str, int] = {}
    for h in history:
        lvl = h.get("risk_level", "NONE")
        level_count[lvl] = level_count.get(lvl, 0) + 1

    summary_lines = ["🔒 **내 PDV (Private Data Vault)**\n"]
    for lvl, cnt in level_count.items():
        emoji = RiskLevel(lvl).emoji
        summary_lines.append(f"  {emoji} {lvl}: {cnt}건")

    summary_lines.append(f"\n**최근 기록** (최대 15개)\n")
    for h in history[:15]:
        risk_emoji = RiskLevel(h["risk_level"]).emoji
        ts = h["timestamp"][:16]
        preview = h["text"][:25] + "…" if len(h["text"]) > 25 else h["text"]
        conf = h.get("confidence", 0)
        conf_str = f" (확신도:{conf})" if conf > 0 else ""
        summary_lines.append(f"{risk_emoji} `{ts}` {preview}{conf_str}")

    summary_lines.append(
        f"\n🔗 최신 블록: `{history[0]['block_hash'][:20]}…`"
    )

    await update.message.reply_text(
        "\n".join(summary_lines), parse_mode="Markdown"
    )

# ── /verify ──────────────────────────────────────────────────────────

async def cmd_verify(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/verify — OpenHash 체인 무결성 검증"""
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 PDV 무결성 검증 중...")

    is_valid = await pdv.verify_chain(user_id)

    if is_valid:
        await update.message.reply_text(
            "✅ **PDV 무결성 검증 통과**\n\n"
            "모든 대화 기록이 OpenHash SHA-256 체인으로 보호되어 있습니다.\n"
            "위변조 흔적이 발견되지 않았습니다.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "🚨 **경고: PDV 무결성 이상 감지**\n\n"
            "일부 기록에서 해시 불일치가 발견되었습니다.\n"
            "즉시 AI City Inc.에 신고해 주세요.\n"
            "tensor.city@gmail.com",
            parse_mode="Markdown",
        )

# ── /analyze ─────────────────────────────────────────────────────────

async def cmd_analyze(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/analyze [내용] — K-Law 상세 분석 요청"""
    user_id = update.effective_user.id

    # 명령어 뒤 텍스트 추출
    args = context.args
    if not args:
        await update.message.reply_text(
            "📋 분석할 내용을 입력해 주세요.\n"
            "예시: `/analyze 이자 연 30%로 돈 빌려줄게`",
            parse_mode="Markdown",
        )
        return

    analyze_text = " ".join(args)
    await update.message.reply_text(f"⚖️ K-Law 분석 중: _{analyze_text}_", parse_mode="Markdown")

    from iddm.engine import iddm_engine
    chat_context = await pdv.load_context(user_id, limit=5)
    analysis, reply = await iddm_engine.analyze(
        user_id=user_id,
        message=analyze_text,
        context=chat_context,
    )

    await update.message.reply_text(reply)

    # PDV 저장
    import asyncio
    asyncio.create_task(pdv.save(
        user_id=user_id,
        text=f"/analyze {analyze_text}",
        analysis=analysis,
        response=reply,
    ))
