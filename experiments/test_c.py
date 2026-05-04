"""
test_c.py — LCAM Inter-Rater Reliability (Cohen's κ)
=====================================================
목적:
  LCAM(Legal Completeness Assessment Methodology) 채점의
  평가자 간 일치도를 측정합니다.

  평가자 구성:
    Rater A : K-Law 시스템 (claude-3-5-sonnet)
    Rater B : K-Law 시스템 (독립 실행, 다른 API 호출)
    Rater C : Plain LLM   (프롬프트 없이)

  측정 지표:
    - Cohen's κ (A↔B, A↔C, B↔C)
    - Weighted κ (6개 축 각각)
    - 축별 평균 점수 분포

입력:
  --input   : 판례 요약 디렉토리 (기본: ./summaries/0_예비)
  --output  : 결과 CSV (기본: ./results/test_c_kappa.csv)
  --n       : 샘플 수 (기본: 60, 1_이론방법론 세트 권장)
  --seed    : 랜덤 시드 (기본: 42)

실행:
  python experiments/test_c.py --input ./summaries/1_이론방법론 --n 60
"""

import os
import sys
import json
import csv
import argparse
import random
import time
from pathlib import Path
from typing import Optional

try:
    from anthropic import Anthropic
except ImportError:
    sys.exit("[ERROR] anthropic 패키지 필요: pip install anthropic")

# ---------------------------------------------------------------------------
# LCAM 축 정의 (6-axis, 100점)
# ---------------------------------------------------------------------------
LCAM_AXES = {
    "A1_사실인정":      {"max": 20, "desc": "사실관계 완전성·정확성"},
    "A2_법령적용":      {"max": 20, "desc": "관련 법령 적용 적정성"},
    "A3_법리판단":      {"max": 20, "desc": "법리 해석의 논리적 일관성"},
    "A4_증거판단":      {"max": 15, "desc": "증거 채택·배척 합리성"},
    "A5_주문명확성":    {"max": 15, "desc": "주문의 명확성·집행 가능성"},
    "A6_이유설시":      {"max": 10, "desc": "판결 이유 충분성"},
}
TOTAL_MAX = sum(v["max"] for v in LCAM_AXES.values())  # 100

# ---------------------------------------------------------------------------
# 프롬프트 로더
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent

def load_prompt(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""  # 파일 없으면 빈 문자열 (Plain LLM 용)

KLAW_SYSTEM   = load_prompt("klaw/prompts/system_prompt.txt")
LCAM_RUBRIC   = load_prompt("klaw/lcam/scoring_rubric.txt")
PLAIN_SYSTEM  = load_prompt("klaw/prompts/plain_llm_prompt.txt")

# ---------------------------------------------------------------------------
# LCAM 채점 요청 (단일 판례)
# ---------------------------------------------------------------------------
def build_lcam_scoring_prompt(case_summary: str) -> str:
    axes_desc = "\n".join(
        f"  {k} (/{v['max']}점): {v['desc']}"
        for k, v in LCAM_AXES.items()
    )
    return f"""다음 사건 요약에 대해 LCAM 6개 축으로 채점하십시오.

[사건 요약]
{case_summary}

[채점 기준]
{axes_desc}

반드시 아래 JSON 형식으로만 응답하십시오. 다른 텍스트 없이:
{{
  "A1_사실인정": <정수>,
  "A2_법령적용": <정수>,
  "A3_법리판단": <정수>,
  "A4_증거판단": <정수>,
  "A5_주문명확성": <정수>,
  "A6_이유설시": <정수>,
  "reasoning": "<한 문장 근거>"
}}
"""

def score_case(
    client: Anthropic,
    case_summary: str,
    system_prompt: str,
    model: str = "claude-sonnet-4-20250514",
    retries: int = 3,
) -> Optional[dict]:
    prompt = build_lcam_scoring_prompt(case_summary)
    for attempt in range(retries):
        try:
            kwargs = {"model": model, "max_tokens": 512,
                      "messages": [{"role": "user", "content": prompt}]}
            if system_prompt:
                kwargs["system"] = system_prompt
            resp = client.messages.create(**kwargs)
            text = resp.content[0].text.strip()
            # JSON 파싱
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            scores = json.loads(text)
            # 범위 클램프
            for k, v in LCAM_AXES.items():
                scores[k] = max(0, min(v["max"], int(scores.get(k, 0))))
            scores["total"] = sum(scores[k] for k in LCAM_AXES)
            return scores
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] 채점 실패: {e}")
                return None

# ---------------------------------------------------------------------------
# Cohen's κ 계산
# ---------------------------------------------------------------------------
def cohens_kappa(ratings_a: list, ratings_b: list, n_categories: int = None) -> float:
    """
    단순 Cohen's κ (카테고리형).
    점수를 5점 단위 구간으로 이산화하여 계산합니다.
    """
    assert len(ratings_a) == len(ratings_b)
    n = len(ratings_a)
    if n == 0:
        return float("nan")

    # 5점 단위 구간화 (0~100 → 0~20 구간)
    def bucket(x, step=5):
        return int(x) // step

    ba = [bucket(x) for x in ratings_a]
    bb = [bucket(x) for x in ratings_b]

    cats = sorted(set(ba) | set(bb))
    cat_idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)

    # 관찰 일치율
    p_o = sum(1 for a, b in zip(ba, bb) if a == b) / n

    # 기대 일치율
    count_a = [ba.count(c) / n for c in cats]
    count_b = [bb.count(c) / n for c in cats]
    p_e = sum(count_a[i] * count_b[i] for i in range(k))

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)

def weighted_kappa_axis(scores_a: list, scores_b: list, axis: str) -> float:
    """축별 weighted κ (linear weights)."""
    max_score = LCAM_AXES[axis]["max"]
    n = len(scores_a)
    if n == 0:
        return float("nan")

    p_o_w = sum(1 - abs(a - b) / max_score for a, b in zip(scores_a, scores_b)) / n

    mean_a = sum(scores_a) / n
    mean_b = sum(scores_b) / n
    # 기대값 (독립 가정, 단순 근사)
    p_e_w = 1 - (
        sum(abs(a - mean_a) for a in scores_a) / (n * max_score) +
        sum(abs(b - mean_b) for b in scores_b) / (n * max_score)
    ) / 2

    if p_e_w >= 1.0:
        return 1.0
    kappa = (p_o_w - p_e_w) / (1.0 - p_e_w)
    return max(-1.0, min(1.0, kappa))

# ---------------------------------------------------------------------------
# 판례 요약 로드
# ---------------------------------------------------------------------------
def load_summaries(input_dir: str, n: int, seed: int) -> list[dict]:
    p = Path(input_dir)
    files = sorted(p.glob("*.json")) + sorted(p.glob("*.txt"))
    random.seed(seed)
    random.shuffle(files)
    files = files[:n]

    summaries = []
    for f in files:
        try:
            if f.suffix == ".json":
                data = json.loads(f.read_text(encoding="utf-8"))
                text = data.get("summary") or data.get("text") or str(data)
            else:
                text = f.read_text(encoding="utf-8")
            summaries.append({"id": f.stem, "text": text[:3000]})
        except Exception as e:
            print(f"  [WARN] {f.name} 로드 실패: {e}")
    return summaries

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LCAM Inter-Rater Reliability (κ)")
    parser.add_argument("--input",  default="./summaries/1_이론방법론",
                        help="판례 요약 디렉토리")
    parser.add_argument("--output", default="./results/test_c_kappa.csv",
                        help="결과 CSV 경로")
    parser.add_argument("--n",      type=int, default=60, help="샘플 수")
    parser.add_argument("--seed",   type=int, default=42, help="랜덤 시드")
    parser.add_argument("--model",  default="claude-sonnet-4-20250514")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("[ERROR] ANTHROPIC_API_KEY 환경변수 필요")

    client = Anthropic(api_key=api_key)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    summaries = load_summaries(args.input, args.n, args.seed)
    if not summaries:
        sys.exit(f"[ERROR] 판례 요약 없음: {args.input}")

    print(f"[test_c] 판례 {len(summaries)}건 로드 완료")
    print(f"[test_c] 3개 평가자 × {len(summaries)}건 = {3*len(summaries)} API 호출")

    rows = []
    totals = {"A": [], "B": [], "C": []}
    axis_scores = {ax: {"A": [], "B": [], "C": []} for ax in LCAM_AXES}

    for i, case in enumerate(summaries, 1):
        print(f"  [{i:03d}/{len(summaries)}] {case['id']}")

        sa = score_case(client, case["text"], KLAW_SYSTEM,   args.model)
        sb = score_case(client, case["text"], KLAW_SYSTEM,   args.model)  # 독립 재실행
        sc = score_case(client, case["text"], PLAIN_SYSTEM,  args.model)

        if not (sa and sb and sc):
            print(f"    [SKIP] 채점 실패")
            continue

        row = {"case_id": case["id"]}
        for ax in LCAM_AXES:
            row[f"{ax}_A"] = sa[ax]
            row[f"{ax}_B"] = sb[ax]
            row[f"{ax}_C"] = sc[ax]
            axis_scores[ax]["A"].append(sa[ax])
            axis_scores[ax]["B"].append(sb[ax])
            axis_scores[ax]["C"].append(sc[ax])

        row["total_A"] = sa["total"]
        row["total_B"] = sb["total"]
        row["total_C"] = sc["total"]
        totals["A"].append(sa["total"])
        totals["B"].append(sb["total"])
        totals["C"].append(sc["total"])
        rows.append(row)

        time.sleep(0.5)  # Rate limit

    if not rows:
        sys.exit("[ERROR] 유효한 결과 없음")

    # --- κ 계산 ---
    kappa_AB = cohens_kappa(totals["A"], totals["B"])
    kappa_AC = cohens_kappa(totals["A"], totals["C"])
    kappa_BC = cohens_kappa(totals["B"], totals["C"])

    print("\n[test_c] ===== 결과 요약 =====")
    print(f"  Cohen's κ (A↔B, K-Law내 일치): {kappa_AB:.4f}")
    print(f"  Cohen's κ (A↔C, K-Law vs Plain): {kappa_AC:.4f}")
    print(f"  Cohen's κ (B↔C, K-Law vs Plain): {kappa_BC:.4f}")
    print(f"  평균 총점 — A: {sum(totals['A'])/len(totals['A']):.1f}, "
          f"B: {sum(totals['B'])/len(totals['B']):.1f}, "
          f"C: {sum(totals['C'])/len(totals['C']):.1f}")

    print("\n  축별 weighted κ (A↔B):")
    for ax in LCAM_AXES:
        wk = weighted_kappa_axis(axis_scores[ax]["A"], axis_scores[ax]["B"], ax)
        print(f"    {ax}: {wk:.4f}")

    # --- CSV 저장 ---
    fieldnames = list(rows[0].keys())
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # --- 요약 JSON 저장 ---
    summary_path = Path(args.output).with_suffix(".summary.json")
    summary = {
        "n": len(rows),
        "kappa_AB_total": round(kappa_AB, 4),
        "kappa_AC_total": round(kappa_AC, 4),
        "kappa_BC_total": round(kappa_BC, 4),
        "mean_total_A": round(sum(totals["A"])/len(totals["A"]), 2),
        "mean_total_B": round(sum(totals["B"])/len(totals["B"]), 2),
        "mean_total_C": round(sum(totals["C"])/len(totals["C"]), 2),
        "weighted_kappa_AB": {
            ax: round(weighted_kappa_axis(
                axis_scores[ax]["A"], axis_scores[ax]["B"], ax), 4)
            for ax in LCAM_AXES
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    print(f"\n[test_c] 결과 저장: {args.output}")
    print(f"[test_c] 요약 저장: {summary_path}")
    print("[test_c] 완료")

if __name__ == "__main__":
    main()
