"""
iddm/fast_path.py — Fast-Path 키워드 탐지 (FP-01 ~ FP-08)
K-Law v13.2 부록 B 트리거 키워드 기반.
목표: < 50ms 처리
"""
from __future__ import annotations
import re
from models.message import RiskLevel, FastPathTrigger

# ── Fast-Path 탐지 규칙 정의 ─────────────────────────────────────────

FP_RULES: list[dict] = [
    {
        "code": "FP-01",
        "name": "계약·금전 관계",
        "keywords": [
            "빌려줄게", "빌려줘", "빌려드릴게", "빌려드려",
            "나중에 줄게", "나중에 갚을게", "나중에 드릴게",
            "이자", "담보", "보증", "차용", "빚", "채무", "갚을게",
            "빌려달라", "꿔줄게", "꿔줘", "꿔달라",
            "원금", "이율", "변제", "상환",
        ],
        "patterns": [
            r"(\d+)(만원|억|천만원).*(빌|꿔|빚|채)",
            r"(빌|꿔).+(\d+)(만원|억|천만원)",
            r"나중에.*(갚|줄|드릴)",
        ],
        "base_level": RiskLevel.CR,
        "escalate_to": RiskLevel.CV,  # 이자율 언급 시 CV로 상승
        "escalate_keywords": ["이자", "이율", r"월 \d+%", r"연 \d+%"],
        "description": "금전 대여·차용 관계 감지 — 구두 약속은 법적 분쟁 시 입증 곤란",
        "legal_basis": "민법 제598조 (소비대차), 이자제한법 제2조 (최고이율 연 20%)",
        "axiom_basis": "공리 I (문서 규범 우선), 공리 C (실질 우선)",
        "action": "금액·상환일·이자를 명시한 차용증 작성 권장",
    },
    {
        "code": "FP-02",
        "name": "부동산·임대",
        "keywords": [
            "전세", "월세", "보증금", "계약금", "중개",
            "임대", "임차", "세입자", "집주인", "건물주",
            "방 빼", "퇴거", "명도", "권리금",
            "전월세", "반전세", "깡통전세",
        ],
        "patterns": [
            r"보증금.*(올려|내려|반환|돌려)",
            r"계약금.*(포기|몰수|돌려)",
            r"(\d+)(만원|억).*(전세|월세|보증)",
        ],
        "base_level": RiskLevel.CR,
        "escalate_to": RiskLevel.CV,
        "escalate_keywords": ["계약서 없이", "구두로", "말로만"],
        "description": "부동산 임대차 관계 감지 — 계약 조건 서면화 필요",
        "legal_basis": "주택임대차보호법, 상가건물임대차보호법",
        "axiom_basis": "공리 I (문서 규범), 공리 H §1.6 (특별법 우선)",
        "action": "임대차 계약서 작성 및 확정일자 취득 권장",
    },
    {
        "code": "FP-03",
        "name": "계약서 회피",
        "keywords": [
            "계약서 필요없어", "계약서 없이", "계약서 안 써도",
            "말로 하자", "말로만 하자", "구두로 하자",
            "그냥 믿어", "믿으면 되잖아", "우리 사이에",
            "서류 필요없어", "도장 안 찍어도",
            "계약서 왜 써", "귀찮게 왜",
        ],
        "patterns": [
            r"(계약서|서류|문서).*(필요없|안 써도|없어도)",
            r"말로.*(하자|하면 돼|해도 돼)",
            r"믿으니까.*(됐어|됐잖아|돼)",
        ],
        "base_level": RiskLevel.CR,
        "escalate_to": RiskLevel.CV,
        "escalate_keywords": [],
        "description": "계약서 작성 회피 — 분쟁 발생 시 입증 불가",
        "legal_basis": "민법 제105조 (임의규정), 증거법 일반 원칙",
        "axiom_basis": "공리 I (문서 규범 우선)",
        "action": "모든 합의사항을 서면으로 작성하고 쌍방 서명 권장",
    },
    {
        "code": "FP-04",
        "name": "노동·고용 관계",
        "keywords": [
            "최저임금", "야근", "퇴직금", "해고", "권고사직",
            "월급", "주급", "일당", "급여", "임금",
            "주 52시간", "연장근무", "특근", "휴가", "연차",
            "4대보험", "근로계약", "취업규칙",
            "실업급여", "고용보험", "산재",
        ],
        "patterns": [
            r"월급.*(안 줘|안 줬|못 받|체불)",
            r"(해고|잘랐|짤렸|권고사직).*(부당|억울|갑자기)",
            r"퇴직금.*(안 줘|못 받|떼먹|안 준다)",
            r"주 \d+시간",
        ],
        "base_level": RiskLevel.CV,
        "escalate_to": RiskLevel.LB,
        "escalate_keywords": ["부당해고", "임금체불", "퇴직금 안 줘", "퇴직금 안 줘도", "퇴직금 못 받"],
        "description": "노동·고용 관계 법령 위반 소지 감지",
        "legal_basis": "근로기준법, 최저임금법, 고용보험법",
        "axiom_basis": "공리 D §3 (약자 보호), 부록 B [노동법]",
        "action": "근로계약서 작성 및 노동청 상담 권장",
    },
    {
        "code": "FP-05",
        "name": "개인정보·사생활 침해",
        "keywords": [
            "주민번호", "주민등록번호", "생년월일 알려줘",
            "개인정보", "몰래", "주소 알려줘", "집 주소",
            "사진 찍", "동영상 찍", "몰카", "불법촬영",
            "위치 추적", "GPS", "감시", "미행",
            "비번 알려줘", "비밀번호",
        ],
        "patterns": [
            r"(몰래|허락없이|모르게).*(찍|촬영|사진|동영상)",
            r"(주소|집|위치|연락처).*(알려줘|가르쳐줘|알아내)",
            r"(핸드폰|스마트폰|카카오).*(해킹|뚫어|들어가)",
        ],
        "base_level": RiskLevel.LB,
        "escalate_to": RiskLevel.CC,
        "escalate_keywords": ["몰래 찍", "불법촬영", "몰카", "해킹"],
        "description": "개인정보 침해·불법촬영 소지 감지",
        "legal_basis": "개인정보보호법 제71조, 성폭력처벌법 제14조 (불법촬영)",
        "axiom_basis": "공리 F (기본권 보호), 공리 H §1 (제재규범 엄격해석)",
        "action": "개인정보 수집은 정보주체 동의 필수. 법률 전문가 상담 권장",
    },
    {
        "code": "FP-06",
        "name": "협박·강요",
        "keywords": [
            "안 하면 두고봐", "가만 안 둬", "후회할걸",
            "신고해버릴", "고소해버릴", "죽여버릴", "죽여버린다",
            "망하게 해줄", "다 말해버릴", "폭로해버릴",
            "협박", "강요", "강제로", "억지로",
            "XX해버릴", "가만있지 않을", "보복",
        ],
        "patterns": [
            r"(안 하면|안 따르면|거부하면).*(두고봐|후회|가만)",
            r"(죽여|죽인다|죽어버려|없애버릴)",
            r"(신고|고소|고발).*(해버릴|해버린다|한다고)",
            r"(다 폭로|다 말해|다 까발려)",
        ],
        "base_level": RiskLevel.LB,
        "escalate_to": RiskLevel.CC,
        "escalate_keywords": ["죽여", "죽인다", "없애버릴"],
        "description": "협박·강요 표현 감지 — 형사처벌 가능",
        "legal_basis": "형법 제283조 (협박죄), 제324조 (강요죄)",
        "axiom_basis": "공리 H §1 (제재규범 엄격해석), 공리 F",
        "action": "해당 메시지 전송 자제 강력 권고. 이미 받았다면 경찰 신고 고려",
    },
    {
        "code": "FP-07",
        "name": "재산 관련 범죄 위험",
        "keywords": [
            "가져다 써", "그냥 가져가", "몰래 가져",
            "빼돌려", "횡령", "배임", "사기",
            "몰래 쓰면 돼", "훔쳐", "없애버려",
            "증거 없애", "증거 인멸", "CCTV 끄",
            "장부 조작", "서류 위조", "도장 위조",
        ],
        "patterns": [
            r"(몰래|허락없이|들키지 말고).*(가져|써|쓰|사용)",
            r"(증거|CCTV|영수증|서류).*(없애|인멸|지워|버려)",
            r"(도장|서명|문서).*(위조|가짜|만들어)",
        ],
        "base_level": RiskLevel.LB,
        "escalate_to": RiskLevel.CC,
        "escalate_keywords": ["증거 인멸", "위조", "사기", "횡령"],
        "description": "재산범죄·증거인멸 소지 감지",
        "legal_basis": "형법 제355조 (횡령·배임), 제347조 (사기), 제155조 (증거인멸)",
        "axiom_basis": "공리 H §1, 공리 F (증거법 원칙)",
        "action": "해당 행위 즉시 중단. 법률 전문가 상담 및 경찰 신고 고려",
    },
    {
        "code": "FP-08",
        "name": "방화·폭발·폭력 위험",
        "keywords": [
            "불 질러", "불 질러버려", "태워버려", "태워버릴",
            "폭탄", "폭발물", "폭발시켜", "터뜨려",
            "때려", "폭행", "살인", "상해",
            "독", "독약", "음독", "약 넣어",
            "가스", "가스 틀어",
        ],
        "patterns": [
            r"(불|화재|방화).*(질러|지르|태워|태울)",
            r"(폭탄|폭발|폭발물).*(만들|터뜨|설치)",
            r"(때려|죽여|폭행|살인|상해).*(버려|버릴|야|라)",
        ],
        "base_level": RiskLevel.CC,
        "escalate_to": RiskLevel.CC,
        "escalate_keywords": [],
        "description": "방화·폭발·폭력 관련 표현 감지 — 형사처벌 가능성 높음",
        "legal_basis": "형법 제164조 (현주건조물방화), 제175조 (방화예비), 제250조 (살인)",
        "axiom_basis": "공리 H §1 (제재규범 엄격해석), 공리 D §1 (생명·신체 최우선)",
        "action": "⛔ 해당 메시지를 전송하지 마십시오. 즉시 법률 전문가와 상담하세요.",
    },
]


class FastPathScanner:
    """
    Fast-Path 키워드 스캐너
    K-Law v13.2 부록 B 트리거 기반 — 목표 50ms 이하
    """

    def __init__(self):
        self._rules = FP_RULES
        # 패턴 미리 컴파일
        self._compiled: list[dict] = []
        for rule in self._rules:
            compiled_patterns = [
                re.compile(p, re.IGNORECASE)
                for p in rule.get("patterns", [])
            ]
            compiled_escalate = [
                re.compile(kw, re.IGNORECASE)
                for kw in rule.get("escalate_keywords", [])
            ]
            self._compiled.append({
                **rule,
                "_compiled_patterns": compiled_patterns,
                "_compiled_escalate": compiled_escalate,
            })

    def scan(self, text: str) -> list[FastPathTrigger]:
        """
        텍스트를 스캔하여 매칭된 Fast-Path 트리거 목록 반환
        매칭 없으면 빈 리스트 반환
        """
        triggers: list[FastPathTrigger] = []
        text_lower = text.lower()

        for rule in self._compiled:
            matched_kws: list[str] = []

            # 1) 키워드 직접 매칭
            for kw in rule["keywords"]:
                if kw.lower() in text_lower:
                    matched_kws.append(kw)

            # 2) 정규식 패턴 매칭
            for pattern in rule["_compiled_patterns"]:
                if pattern.search(text):
                    matched_kws.append(f"패턴:{pattern.pattern[:20]}")

            if not matched_kws:
                continue

            # 3) 에스컬레이션 확인
            risk_level = rule["base_level"]
            if rule.get("escalate_to") and rule["escalate_to"] != risk_level:
                for esc in rule["_compiled_escalate"]:
                    if esc.search(text):
                        risk_level = rule["escalate_to"]
                        break

            triggers.append(FastPathTrigger(
                fp_code=rule["code"],
                matched_keywords=matched_kws[:5],  # 최대 5개만
                suggested_level=risk_level,
                description=rule["description"],
            ))

        return triggers

    def get_rule_detail(self, fp_code: str) -> dict | None:
        """FP 코드로 규칙 상세 조회"""
        for rule in self._rules:
            if rule["code"] == fp_code:
                return rule
        return None

    def get_highest_level(self, triggers: list[FastPathTrigger]) -> RiskLevel:
        """트리거 목록에서 최고 위험 등급 반환"""
        if not triggers:
            return RiskLevel.NONE
        return max(triggers, key=lambda t: t.suggested_level.severity).suggested_level
