"""
openclaw/client.py — DeepSeek v4 Pro API 클라이언트 (OpenClaw)
"""
from __future__ import annotations
import re
import json
import logging
import httpx
from config import config
from models.message import RiskLevel, AnalysisResult, AxiomResult, FastPathTrigger
from openclaw.prompts import build_session_prompt, build_analysis_prompt

logger = logging.getLogger(__name__)

# 세션별 시스템 프롬프트 캐시 {user_id: prompt}
_session_cache: dict[int, str] = {}


class OpenClawClient:
    """
    OpenClaw — DeepSeek v4 Pro 기반 AI 비서 클라이언트
    K-Law Gopang v1.0 방법론 내장
    """

    def __init__(self):
        self._base_url = config.DEEPSEEK_BASE_URL
        self._api_key = config.DEEPSEEK_API_KEY
        self._model = config.DEEPSEEK_MODEL

    def init_session(self, user_id: int, context_summary: str = "") -> None:
        """봇 시작 시 K-Law Gopang v1.0 시스템 프롬프트 주입"""
        _session_cache[user_id] = build_session_prompt(user_id, context_summary)
        logger.info(f"[OpenClaw] 세션 초기화 완료 — user_id={user_id}")

    def get_system_prompt(self, user_id: int) -> str:
        if user_id not in _session_cache:
            self.init_session(user_id)
        return _session_cache[user_id]

    async def analyze_and_respond(
        self,
        user_id: int,
        user_message: str,
        chat_context: list[dict],
        fp_triggers: list[FastPathTrigger],
    ) -> tuple[AnalysisResult, str]:
        """
        메시지 분석 + 응답 생성 (단일 API 호출로 처리)
        반환: (AnalysisResult, 사용자에게 보낼 최종 텍스트)
        """
        # Fast-Path 결과 요약
        fp_summary = self._format_fp_summary(fp_triggers)

        # 프롬프트 구성
        messages = build_analysis_prompt(
            user_message=user_message,
            chat_context=chat_context,
            fp_result_summary=fp_summary,
        )

        # DeepSeek API 호출
        raw_response = await self._call_deepseek(
            system_prompt=self.get_system_prompt(user_id),
            messages=messages,
            temperature=0.1,  # 법률 분석은 낮게
        )

        # 응답 파싱
        analysis, user_reply = self._parse_response(raw_response, fp_triggers)
        return analysis, user_reply

    async def _call_deepseek(
        self,
        system_prompt: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> str:
        """DeepSeek API 호출"""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(
        self,
        raw: str,
        fp_triggers: list[FastPathTrigger],
    ) -> tuple[AnalysisResult, str]:
        """
        DeepSeek 응답에서 IDDM 분석 결과와 사용자 응답을 분리 파싱.
        형식:
          [IDDM 분석]
          - 위험등급: CR
          - 확신도: 6
          ...
          [사용자 응답]
          ...
        """
        analysis_block = ""
        user_reply_block = raw.strip()

        # [IDDM 분석] 블록 추출
        iddm_match = re.search(
            r'\[IDDM 분석\](.*?)(?:\[사용자 응답\]|$)',
            raw, re.DOTALL
        )
        user_match = re.search(
            r'\[사용자 응답\](.*?)$',
            raw, re.DOTALL
        )

        if iddm_match:
            analysis_block = iddm_match.group(1).strip()
        if user_match:
            user_reply_block = user_match.group(1).strip()

        # IDDM 블록 파싱
        risk_level = self._extract_risk_level(analysis_block, fp_triggers)
        confidence = self._extract_confidence(analysis_block)
        risk_summary = self._extract_field(analysis_block, "핵심위험")
        legal_basis = self._extract_field(analysis_block, "법령근거")
        axiom_basis = self._extract_field(analysis_block, "공리적용")
        action = self._extract_field(analysis_block, "권장조치")

        # 경고 메시지 생성
        warning_msg = ""
        if risk_level != RiskLevel.NONE and confidence >= config.IDDM_CONFIDENCE_THRESHOLD:
            warning_msg = self._build_warning_message(
                risk_level, risk_summary, legal_basis, axiom_basis, action
            )

        analysis = AnalysisResult(
            risk_level=risk_level,
            confidence=confidence,
            fp_triggers=fp_triggers,
            axiom_result=AxiomResult(
                proposition_p="",
                proposition_q="",
                confidence=confidence,
            ),
            risk_summary=risk_summary,
            legal_basis=legal_basis,
            axiom_basis=axiom_basis,
            recommended_action=action,
            warning_message=warning_msg,
        )

        # 최종 사용자 메시지 = 경고 + 응답
        final_reply = ""
        if warning_msg:
            final_reply = warning_msg + "\n\n" + "─" * 30 + "\n\n"
        final_reply += user_reply_block

        return analysis, final_reply

    # ── 파싱 헬퍼 ─────────────────────────────────────────────────────

    def _extract_risk_level(
        self, block: str, fp_triggers: list[FastPathTrigger]
    ) -> RiskLevel:
        """위험등급 추출 (Fast-Path 결과와 비교해 더 높은 값 선택)"""
        # LLM 응답에서 추출
        m = re.search(r'위험등급[:\s]*([A-Z]+)', block)
        llm_level = RiskLevel.NONE
        if m:
            try:
                llm_level = RiskLevel(m.group(1).strip())
            except ValueError:
                pass

        # Fast-Path 최고 등급
        fp_level = RiskLevel.NONE
        if fp_triggers:
            fp_level = max(
                fp_triggers,
                key=lambda t: t.suggested_level.severity
            ).suggested_level

        # 더 높은 등급 선택
        if fp_level.severity > llm_level.severity:
            return fp_level
        return llm_level

    def _extract_confidence(self, block: str) -> int:
        m = re.search(r'확신도[:\s]*(\d+)', block)
        if m:
            return min(10, max(0, int(m.group(1))))
        return 0

    def _extract_field(self, block: str, field: str) -> str:
        m = re.search(rf'{field}[:\s]*(.+?)(?:\n|$)', block)
        if m:
            return m.group(1).strip()
        return ""

    def _build_warning_message(
        self,
        risk_level: RiskLevel,
        risk_summary: str,
        legal_basis: str,
        axiom_basis: str,
        action: str,
    ) -> str:
        """표준 경고 메시지 생성"""
        lines = [
            f"⚠️ [{risk_level.value}] K-Law Gopang 예방 경고",
            "",
            f"📋 탐지된 위험: {risk_summary or '위법·분쟁 소지 탐지'}",
        ]
        if legal_basis:
            lines.append(f"📚 관련 법령: {legal_basis}")
        if axiom_basis:
            lines.append(f"⚖️ 판단 근거: {axiom_basis}")
        if action:
            lines.append(f"💡 권장 조치: {action}")
        lines.append("🔒 PDV 기록: 완료 (위변조 불가)")
        return "\n".join(lines)

    @staticmethod
    def _format_fp_summary(triggers: list[FastPathTrigger]) -> str:
        if not triggers:
            return ""
        lines = []
        for t in triggers:
            kws = ", ".join(t.matched_keywords[:3])
            lines.append(
                f"• {t.fp_code} [{t.suggested_level.value}]: {t.description} (키워드: {kws})"
            )
        return "\n".join(lines)


# 싱글턴
openclaw = OpenClawClient()
