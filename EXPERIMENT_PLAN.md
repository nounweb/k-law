# PLAS 실험계획서 (Pre-Registration Plan)

> 버전: v1.0 | 작성일: 2026-05-04  
> 저자: 도영민 (Young-Min Do) · 박용철 교수 (Prof. Yong-Chul Park)  
> ORCID: 0009-0004-4288-8746  
> OSF 사전등록 예정 | 저장소: https://github.com/nounweb/k-law

---

## 1. 연구 개요

### 1.1 연구 제목
**PLAS: AI 기반 예방법학 시스템의 실증적 검증**  
*Empirical Validation of PLAS: A Preventive Legal Autonomy System*

### 1.2 핵심 가설

| 번호 | 가설 | 검증 실험 |
|------|------|-----------|
| H1 | K-Law가 Plain LLM보다 LCAM 점수가 유의미하게 높다 | test_b, test_d |
| H2 | K-Law의 LCAM 점수는 대법원 판결 수준에 근접한다 (±10점) | test_d |
| H3 | LCAM 평가자 간 일치도 κ ≥ 0.70 (신뢰 가능 수준) | test_c |
| H4 | IDDM이 Plain LLM보다 위법성 탐지 F1이 유의미하게 높다 | test_e |
| H5 | IDDM FP-01~08 각각의 탐지율 ≥ 70% | test_e |

---

## 2. 데이터 설계

### 2.1 전체 데이터 구조

```
전체 1,000건 (법제처 Open API, seed=42 층화 분할)
│
├── 개발용 409건 (자유롭게 사용, 방법론 개발)
│   ├── 0_예비         349건  ← 예비실험 (K-Law v14.0 개선)
│   └── 1_이론방법론    60건  ← 논문 예시, test_c
│
└── 본 실험용 590건 (OSF 사전등록 후 봉인, seed=42 고정)
    ├── 2_KLaw_실험    200건  ← test_b 주요 비교
    ├── 2_Anchor_Set   100건  ← test_a 앵커 검증
    ├── 2_법원비교_추가  40건  ← test_d 3단계 비교
    └── 3_시스템응용   250건  ← test_e + 통합 검증
```

### 2.2 판례 수집 기준

- **출처**: 법제처 국가법령정보센터 Open API (공개 데이터)
- **기간**: 2015-01-01 ~ 2025-12-31
- **분야**: 민사(40%) · 형사(30%) · 행정(20%) · 기타(10%)
- **심급**: 1심·2심·대법원 혼합
- **수집 스크립트**: `data/collect_1008.py`
- **전처리**: 판결 결과(주문) 제거 후 사건 요약만 추출 (`data/summary_1008.py`)
- **분할**: 층화 랜덤 분할, seed=42 (`data/split_final.py`)

---

## 3. 실험 설계

### 3.1 예비실험 (0_예비 349건) — K-Law v14.0 개선

**목적**: 방법론 반복 개선, 본 실험 전 버전 확정

```
반복 사이클:
  1. Plain LLM Baseline 측정 (test_b 로직 적용)
  2. K-Law 현재 버전 성능 측정
  3. 약점 분석 → 프롬프트/공리 수정
  4. 재측정 → 수렴 시 v14.0 확정
```

**확정 조건**: LCAM 평균 점수 개선 < 0.5점 (3회 연속) → 버전 동결

---

### 3.2 test_a — K-Law vs 법원 판결 앵커 검증

| 항목 | 내용 |
|------|------|
| 파일 | `experiments/test_a.py` |
| 데이터 | `2_Anchor_Set` 100건 |
| 비교 | K-Law 가상 판결 ↔ 실제 법원 판결 |
| 측정 | LCAM 6축 점수, 주문 일치율 |
| 출력 | `results/test_a_results.csv` |
| 논문 | 논문 2 (§4.1) |

**판단 기준**:
- K-Law LCAM 점수 > 법원 판결 LCAM 점수: H1 지지
- 주문 일치율 ≥ 70%: 실용적 신뢰성 입증

---

### 3.3 test_b — K-Law vs Plain LLM 3종 비교

| 항목 | 내용 |
|------|------|
| 파일 | `experiments/test_b.py` |
| 데이터 | `2_KLaw_실험` 200건 |
| 조건 | A: K-Law / B: GPT-4o plain / C: Claude plain / D: DeepSeek plain |
| 측정 | LCAM 6축 100점, 응답 시간 |
| 통계 | 대응 t검정, Cohen's d, 95% CI |
| 출력 | `results/test_b_results.csv` |
| 논문 | 논문 2 (§4.2) |

**판단 기준**:
- K-Law LCAM ─ Plain LLM LCAM > 0, p < 0.05: H1 지지
- Cohen's d ≥ 0.5 (중간 효과): 실용적 유의성

---

### 3.4 test_c — LCAM 평가자 간 일치도 (κ)

| 항목 | 내용 |
|------|------|
| 파일 | `experiments/test_c.py` |
| 데이터 | `1_이론방법론` 60건 |
| 평가자 | A: K-Law 독립실행 1 / B: K-Law 독립실행 2 / C: Plain LLM |
| 측정 | Cohen's κ (전체), Weighted κ (축별) |
| 출력 | `results/test_c_kappa.csv` |
| 논문 | 논문 1 (§3.4), 논문 2 (§3.2) |

**판단 기준**:
- κ(A↔B) ≥ 0.70: LCAM이 신뢰 가능한 측정 도구 (H3 지지)
- κ(A↔C) < κ(A↔B): K-Law 일관성이 Plain LLM보다 우수

---

### 3.5 test_d — 1·2심 vs K-Law vs 대법원 3단계 비교

| 항목 | 내용 |
|------|------|
| 파일 | `experiments/test_d.py` |
| 데이터 | `2_법원비교_추가` 40건 (3심 모두 있는 판례) |
| 비교 | T1: 원심 / T2: K-Law / T3: 대법원 |
| 측정 | LCAM 6축, 대응 t검정, Cohen's d |
| 출력 | `results/test_d_results.csv` |
| 논문 | 논문 2 (§4.3) |

**판단 기준**:
- LCAM(T2) > LCAM(T1), p < 0.05: K-Law가 원심보다 우수 (H2 일부)
- |LCAM(T2) - LCAM(T3)| ≤ 10점: 대법원 수준 근접 (H2 지지)

---

### 3.6 test_e — IDDM 위법성 탐지 시뮬레이션

| 항목 | 내용 |
|------|------|
| 파일 | `experiments/test_e.py` |
| 데이터 | `3_시스템응용` 250건 또는 내장 샘플 |
| 조건 | A: IDDM 적용 / B: Plain LLM |
| 측정 | Precision, Recall, F1, FPR, 응답시간(ms) |
| FP 분류 | FP-01~FP-08 별도 집계 |
| 출력 | `results/test_e_simulation.csv` |
| 논문 | 논문 3 (§4) |

**판단 기준**:
- F1(IDDM) > F1(Plain), p < 0.05: H4 지지
- FP-01~08 각 탐지율 ≥ 70%: H5 지지

---

## 4. 실행 순서

```bash
# 환경 설정
cp .env.example .env
# .env에 ANTHROPIC_API_KEY 입력
pip install -r requirements.txt

# Step 0: 예비실험 (방법론 개선, 반복)
python experiments/test_a.py --input ./summaries/0_예비 --n 349

# --- OSF 사전등록 (K-Law v14.0 확정 후) ---

# Step 1: 앵커 검증
python experiments/test_a.py --input ./summaries/2_Anchor_Set --n 100

# Step 2: K-Law vs Plain LLM
python experiments/test_b.py --input ./summaries/2_KLaw_실험 --n 200

# Step 3: LCAM 신뢰도
python experiments/test_c.py --input ./summaries/1_이론방법론 --n 60

# Step 4: 3단계 비교
python experiments/test_d.py --input ./summaries/2_법원비교_추가 --n 40

# Step 5: IDDM 탐지
python experiments/test_e.py --n 100

# Step 6: 통계 분석
python experiments/analyze.py --results ./results
```

---

## 5. 통계 분석 계획

| 분석 | 방법 | 도구 |
|------|------|------|
| 집단 비교 | 대응 t검정 (paired t-test) | `analyze.py` |
| 효과 크기 | Cohen's d | `analyze.py` |
| 신뢰도 | Cohen's κ, Weighted κ | `test_c.py` |
| 분류 성능 | Precision/Recall/F1 | `test_e.py` |
| 유의 수준 | α = 0.05 (양측) | — |
| 다중 비교 | Bonferroni 보정 적용 | `analyze.py` |

---

## 6. 버전 관리

| 단계 | K-Law 버전 | 상태 |
|------|-----------|------|
| 예비실험 진행 중 | v13.x ~ v14.0 | 개발 중 |
| OSF 사전등록 시 | v14.0 | **고정** |
| 본 실험 | v14.0 | 변경 불가 |
| 논문 게재 후 | v14.1+ | 공개 갱신 |

> K-Law 프롬프트는 `klaw/prompts/system_prompt.txt`에 버전 태그와 함께 관리됩니다.

---

## 7. 재현 가능성 선언

본 실험의 모든 데이터·코드·프롬프트는 공개됩니다.  
심사관·독자·후속 연구자는 법제처 공개 판례를 이용하여  
언제든지 독립적으로 본 연구를 재현하고 확장할 수 있습니다.

```
"This is not a static paper.
 It is a living, continuously verifiable empirical claim."
```

---

## 8. 윤리 선언

- 사용 판례: 법제처 공개 API (공공데이터포털 이용약관 준수)
- 개인정보: 판결문 내 개인정보는 수집하지 않음 (익명 처리된 공개 판례만 사용)
- 이해충돌: 없음

---

*본 문서는 OSF(Open Science Framework) 사전등록 시 제출됩니다.*  
*등록 후에는 실험 조건, 가설, 분석 방법을 변경하지 않습니다.*
