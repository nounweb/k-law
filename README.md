# PLAS: Preventive Legal Autonomy System

**Park-Do PLAS** — OpenHash 기반 AI 자율 분쟁 예방·해결 시스템

> Co-developed by Professor Yong-Chul Park and Developer Young-Min Do  
> AI City Inc. · K-Law Research Group · Jeju, Republic of Korea  
> ORCID: [0009-0004-4288-8746](https://orcid.org/0009-0004-4288-8746)

---

## 핵심 주장 (PD-TJM: Park-Do Tripartite Justice Model)

```
전체 분쟁의 90% → Gopang AI 비서가 소통 시점에서 예방
           9% → K-Law + 변호사 중재로 수분 내 해결
           1% → 인간 법원 (판례 창출 + 입법 1단계)
```

---

## 🔴 실시간 검증 가능성 (Live Verifiability)

본 연구의 가장 중요한 특징입니다.

**심사관·독자·후속 연구자 누구나, 언제든지, 새로운 판례로 독립 검증할 수 있습니다.**

대한민국 대법원은 법제처 Open API를 통해 판례를 지속적으로 공개합니다.
본 논문 작성 시점(2026년 5월 2일)과 논문 심사·출판·구독 시점의 판례는 다릅니다.
이것은 한계가 아니라 강점입니다.

```
서로 다른 시점의 새로운 판례로 동일한 결과가 재현된다면,
K-Law의 우위가 특정 데이터셋에 과적합된 것이 아니라
방법론의 구조적 우위임이 입증됩니다.
```

### 5분 내 재현 방법

```bash
# 1. 저장소 클론
git clone https://github.com/team-jupeter/PLAS.git
cd PLAS

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 최신 판례 수집 (법제처 Open API)
python data/collect_1008.py --count 100 --domains 민사,형사,행정

# 4. 사건 요약 추출 (판결 결과 제거)
python data/summary_batch.py --input ./cases --output ./summaries

# 5. K-Law 가상 판결 생성
python experiments/test_a.py --input ./summaries --output ./results

# 6. 결과 분석
python experiments/analyze.py --results ./results
```

---

## 저장소 구조

```
PLAS/
├── data/                          # 데이터 수집 파이프라인
│   ├── collect_1008.py            # 법제처 API 판례 수집
│   ├── fetch_prec_texts.py        # 판결문 본문 수집
│   ├── summary_batch.py           # gpt-4o-mini 요약 추출
│   └── split_final.py             # 실험군 층화 분할 (seed=42)
│
├── klaw/                          # K-Law 핵심 방법론
│   ├── prompts/                   # K-Law 시스템 프롬프트 전체
│   │   ├── system_prompt.txt      # 15개 공리 + Axiom B
│   │   ├── reverse_reasoning.txt  # 역방향 추론 프로토콜
│   │   └── plain_llm_prompt.txt   # Plain LLM 비교용 공통 프롬프트
│   ├── lcam/                      # LCAM 채점 방법론
│   │   ├── LCAM_full.txt          # LCAM 전문 (Phase 0~8)
│   │   ├── scoring_rubric.txt     # 채점 기준 상세
│   │   └── error_types.txt        # 9개 논리 오류 유형 정의
│   └── iddm/                      # IDDM 예방방법론
│       ├── IDDM_full.txt          # Phase 0~6 전문
│       ├── fast_path.txt          # FP-01~08 즉각 탐지 목록
│       └── risk_indicators.txt    # CR/CV/LB/CC 위험 지표
│
├── experiments/                   # 실험 실행 스크립트
│   ├── test_a.py                  # K-Law vs 법원 판결 비교
│   ├── test_b.py                  # K-Law vs Plain LLM 3종
│   ├── test_c.py                  # LCAM 평가자 간 κ 측정
│   ├── test_d.py                  # 1·2심 vs K-Law vs 대법원
│   ├── test_e.py                  # AI 비서 탐지 시뮬레이션
│   └── analyze.py                 # 통계 분석 (t검정·Cohen's d·κ)
│
├── results/                       # 실험 결과 원본 데이터
│   ├── test_a_results.csv
│   ├── test_b_results.csv
│   ├── test_c_kappa.csv
│   ├── test_d_results.csv
│   └── test_e_simulation.csv
│
├── papers/                        # 논문 초안
│   ├── paper1_theory.txt
│   ├── paper2_empirical.txt
│   └── paper3_system.txt
│
├── requirements.txt               # Python 의존성
├── .env.example                   # API 키 템플릿
└── README.md                      # 본 문서
```

---

## 방법론 명명 체계

| 약어 | 전체 이름 | 설명 |
|------|-----------|------|
| PLAS | Preventive Legal Autonomy System | 통합 시스템 |
| LCAM | Legal Completeness Assessment Methodology | 판결 품질 평가 |
| IDDM | Illegality Detection & Deterrence Methodology | 예방방법론 |
| PD-TJM | Park-Do Tripartite Justice Model | 90-9-1 분쟁 배분 |

---

## 시스템 구성

```
PLAS
├── OpenHash    위변조 불가 소통 기록 보전 (신뢰 기반)
├── K-Law       공리 기반 AI 가상 판결 생성 (판결 엔진)
└── Gopang      실시간 위법성 감지 소통 플랫폼 (예방 채널)
```

---

## 논문 시리즈

| 논문 | 제목 | 투고 목표 |
|------|------|-----------|
| 논문 1 | 이론 및 방법론 | AI & Law (Springer) |
| 논문 2 | 실증적 검증 | Journal of Empirical Legal Studies |
| 논문 3 | 시스템 및 응용 | Computers & Security |

---

## K-Law 버전 이력

| 버전 | 주요 변경 | 비고 |
|------|-----------|------|
| v1.0 | 초기 공리 체계 | 내부 실험 |
| ... | 반복 개선 | 수백 건 실험 |
| v13.2 | 논문 작성 기준 버전 | 2026년 5월 2일 |
| v14.0+ | 지속 갱신 중 | OSF 등록 후 본 실험용 버전 고정 |

> K-Law 방법론은 거의 매일 버전 업데이트가 진행됩니다.
> 본 실험에 사용된 버전은 OSF 사전등록 시 고정됩니다.

---

## OpenHash 특허

- 특허출원 제10-2026-0018910호
- 특허출원 제10-2025-0183149호

---

## 재현 가능성 선언

본 연구의 모든 데이터·코드·프롬프트는 공개됩니다.
심사관·독자·후속 연구자는 법제처 공개 판례를 이용하여
언제든지 독립적으로 본 연구를 재현하고 확장할 수 있습니다.

```
"This is not a static paper. It is a living, continuously
 verifiable empirical claim."
```

---

## 라이선스

MIT License — 자유롭게 사용·수정·배포 가능

## 연락처

tensor.city@gmail.com  
www.openhash.kr
