"""
bot/keyboards.py — Telegram 인라인 키보드 생성
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models.message import RiskLevel


def build_warning_keyboard(risk_level: RiskLevel) -> InlineKeyboardMarkup:
    """위험 등급별 인라인 버튼"""
    if risk_level == RiskLevel.CC:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ 취소하고 다시 작성", callback_data="cancel_msg"),
                InlineKeyboardButton("⚠️ 그래도 전송", callback_data="force_send"),
            ],
            [InlineKeyboardButton("📋 K-Law 상세 분석", callback_data="full_analyze")],
            [InlineKeyboardButton("🔒 내 PDV 기록 보기", callback_data="view_pdv")],
        ])
    elif risk_level == RiskLevel.LB:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 K-Law 상세 분석", callback_data="full_analyze")],
            [InlineKeyboardButton("🔒 내 PDV 기록 보기", callback_data="view_pdv")],
        ])
    elif risk_level in (RiskLevel.CR, RiskLevel.CV):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 K-Law 상세 분석", callback_data="full_analyze")],
        ])
    return InlineKeyboardMarkup([])


def build_start_keyboard() -> InlineKeyboardMarkup:
    """시작 화면 키보드"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 사용법 보기", callback_data="help"),
            InlineKeyboardButton("🔒 내 PDV 보기", callback_data="view_pdv"),
        ],
        [InlineKeyboardButton("⚖️ K-Law 분석 요청", callback_data="full_analyze")],
    ])
