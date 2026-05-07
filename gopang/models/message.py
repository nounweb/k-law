"""
models/message.py — 고팡 핵심 데이터 모델
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class RiskLevel(str, Enum):
    """IDDM 위험 등급"""
    NONE = "NONE"   # 위험 없음
    CR = "CR"       # Contract Risk — 계약 위험 🟡
    CV = "CV"       # Contract Violation — 법령 위반 🟠
    LB = "LB"       # Legal Boundary — 법적 경계 🔴
    CC = "CC"       # Criminal Concern — 형사 우려 🚫

    @property
    def emoji(self) -> str:
        return {
            RiskLevel.NONE: "✅",
            RiskLevel.CR:   "🟡",
            RiskLevel.CV:   "🟠",
            RiskLevel.LB:   "🔴",
            RiskLevel.CC:   "🚫",
        }[self]

    @property
    def label(self) -> str:
        return {
            RiskLevel.NONE: "정상",
            RiskLevel.CR:   "계약 위험",
            RiskLevel.CV:   "법령 위반",
            RiskLevel.LB:   "법적 경계",
            RiskLevel.CC:   "형사 우려",
        }[self]

    @property
    def severity(self) -> int:
        """심각도 점수 (높을수록 위험)"""
        return {"NONE": 0, "CR": 1, "CV": 2, "LB": 3, "CC": 4}[self.value]

    def should_warn(self) -> bool:
        return self != RiskLevel.NONE

    def should_offer_block(self) -> bool:
        return self in (RiskLevel.LB, RiskLevel.CC)


@dataclass
class FastPathTrigger:
    """Fast-Path 트리거 탐지 결과"""
    fp_code: str          # FP-01 ~ FP-08
    matched_keywords: list[str]
    suggested_level: RiskLevel
    description: str


@dataclass
class AxiomResult:
    """K-Law 공리 적용 결과"""
    # 공리 A: 명제 추출
    proposition_p: str    # 발신자 의도
    proposition_q: str    # 수신자 입장 법적 쟁점
    hidden_issues: list[str] = field(default_factory=list)

    # 공리 B: 역방향 검증
    counter_argument: str = ""  # 위험 없는 해석 가능성
    is_false_positive: bool = False

    # 공리 C: 실질 판단
    substance_analysis: str = ""

    # 공리 H: 해석 우선순위
    interpretation_method: str = ""  # 적용된 해석 방법

    # 공리 E: 인과 분해 (필요 시)
    causal_analysis: str = ""

    # 신뢰도
    confidence: int = 0  # 0~10


@dataclass
class AnalysisResult:
    """IDDM 전체 분석 결과"""
    risk_level: RiskLevel
    confidence: int = 0          # 0~10
    fp_triggers: list[FastPathTrigger] = field(default_factory=list)
    axiom_result: AxiomResult | None = None

    # 경고 메시지 구성요소
    risk_summary: str = ""       # 1줄 위험 요약
    legal_basis: str = ""        # 관련 법령
    axiom_basis: str = ""        # 판단 근거 (공리)
    recommended_action: str = "" # 권장 조치
    alternative_text: str = ""   # 대안 표현 제안

    # 완성된 경고 메시지
    warning_message: str = ""

    # 메타
    analyzed_at: datetime = field(default_factory=datetime.now)
    processing_ms: int = 0


@dataclass
class GopangMessage:
    """고팡 메시지 (PDV 저장 단위)"""
    user_id: int
    text: str
    analysis: AnalysisResult | None
    openclaw_response: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = ""         # OpenHash 서명 ID
