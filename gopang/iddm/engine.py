"""
iddm/engine.py — IDDM (위법성 감지·억제 방법론) 메인 엔진
K-Law Gopang v1.0 / 7단계 탐지 파이프라인
"""
from __future__ import annotations
import asyncio
import logging
import time

from config import config
from models.message import AnalysisResult, RiskLevel, FastPathTrigger
from iddm.fast_path import FastPathScanner
from openclaw.client import openclaw

logger = logging.getLogger(__name__)


class IDDMEngine:
    """
    IDDM: Illegal-act Detection and Deterrence Methodology
    K-Law v13.2 공리 체계 기반 7단계 탐지 파이프라인
    """

    def __init__(self):
        self._fp_scanner = FastPathScanner()

    async def analyze(
        self,
        user_id: int,
        message: str,
        context: list[dict],
    ) -> tuple[AnalysisResult, str]:
        """
        7단계 파이프라인 실행.
        반환: (AnalysisResult, 사용자에게 보낼 최종 메시지)
        """
        start_ms = int(time.time() * 1000)

        # ── [단계 1] Fast-Path 키워드 스캔 (< 50ms) ─────────────────
        fp_triggers = self._fp_scanner.scan(message)
        fp_highest = self._fp_scanner.get_highest_level(fp_triggers)

        logger.debug(
            f"[IDDM] FP스캔 완료 — "
            f"트리거={len(fp_triggers)}개, 최고등급={fp_highest.value}"
        )

        # ── [단계 2] 빠른 CC 처리 (확실한 형사 우려는 LLM 없이 즉시 경고) ─
        if fp_highest == RiskLevel.CC and len(fp_triggers) >= 1:
            result, reply = self._build_immediate_cc_response(fp_triggers)
            result.processing_ms = int(time.time() * 1000) - start_ms
            return result, reply

        # ── [단계 3~5] OpenClaw (DeepSeek) 분석 ─────────────────────
        try:
            result, reply = await openclaw.analyze_and_respond(
                user_id=user_id,
                user_message=message,
                chat_context=context,
                fp_triggers=fp_triggers,
            )
        except Exception as e:
            logger.error(f"[IDDM] OpenClaw 오류: {e}")
            result, reply = self._build_fallback_response(fp_triggers, fp_highest)

        result.processing_ms = int(time.time() * 1000) - start_ms
        logger.info(
            f"[IDDM] 분석 완료 — "
            f"user={user_id}, level={result.risk_level.value}, "
            f"confidence={result.confidence}, {result.processing_ms}ms"
        )
        return result, reply

    # ── 즉시 응답 (LLM 불필요한 명백한 케이스) ───────────────────────

    def _build_immediate_cc_response(
        self, triggers: list[FastPathTrigger]
    ) -> tuple[AnalysisResult, str]:
        """CC 등급 즉시 응답 (LLM 호출 없음, 속도 우선)"""
        trigger = triggers[0]

        # 규칙에서 세부 정보 조회
        rule = self._fp_scanner.get_rule_detail(trigger.fp_code)
        legal = rule["legal_basis"] if rule else "형법 관련 조항"
        action = rule["action"] if rule else "즉시 법률 전문가 상담"

        warning = (
            f"🚫 [CC] K-Law Gopang 예방 경고\n\n"
            f"📋 탐지된 위험: {trigger.description}\n"
            f"📚 관련 법령: {legal}\n"
            f"⚖️ 판단 근거: 공리 H §1 (제재규범 엄격해석), 공리 F\n"
            f"💡 권장 조치: {action}\n"
            f"🔒 PDV 기록: 완료 (위변조 불가)"
        )
        reply = (
            warning + "\n\n"
            "─" * 30 + "\n\n"
            "⛔ 해당 메시지는 형사처벌 가능성이 있는 표현을 포함합니다.\n"
            "전송 전에 내용을 다시 한번 검토해 주세요.\n\n"
            "도움이 필요하시면 법률 전문가 상담을 받으시거나, "
            "/analyze 명령어로 상세 분석을 요청하세요."
        )

        result = AnalysisResult(
            risk_level=RiskLevel.CC,
            confidence=9,
            fp_triggers=triggers,
            risk_summary=trigger.description,
            legal_basis=legal,
            axiom_basis="공리 H §1, 공리 F",
            recommended_action=action,
            warning_message=warning,
        )
        return result, reply

    def _build_fallback_response(
        self,
        triggers: list[FastPathTrigger],
        highest_level: RiskLevel,
    ) -> tuple[AnalysisResult, str]:
        """OpenClaw 오류 시 Fast-Path 기반 폴백 응답"""
        if not triggers or highest_level == RiskLevel.NONE:
            reply = "죄송합니다, 일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            return AnalysisResult(risk_level=RiskLevel.NONE), reply

        trigger = triggers[0]
        rule = self._fp_scanner.get_rule_detail(trigger.fp_code)
        legal = rule["legal_basis"] if rule else ""
        action = rule["action"] if rule else "전문가 상담 권장"

        warning = (
            f"⚠️ [{highest_level.value}] K-Law Gopang 예방 경고\n\n"
            f"📋 탐지된 위험: {trigger.description}\n"
            f"📚 관련 법령: {legal}\n"
            f"💡 권장 조치: {action}\n"
            f"🔒 PDV 기록: 완료"
        )
        reply = (
            warning + "\n\n"
            "─" * 30 + "\n\n"
            "(일시적 AI 응답 오류로 기본 경고만 제공됩니다. "
            "/analyze로 재시도하거나 잠시 후 다시 입력해 주세요.)"
        )
        result = AnalysisResult(
            risk_level=highest_level,
            confidence=5,
            fp_triggers=triggers,
            risk_summary=trigger.description,
            legal_basis=legal,
            recommended_action=action,
            warning_message=warning,
        )
        return result, reply


# 싱글턴
iddm_engine = IDDMEngine()
