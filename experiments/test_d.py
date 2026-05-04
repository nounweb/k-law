"""
test_d.py — Tripartite Comparison: 1·2심 vs K-Law vs 대법원
============================================================
목적:
  동일 사건에 대해 3가지 판결을 LCAM으로 비교합니다.
    T1 : 1심 또는 2심 판결 (원심)
    T2 : K-Law 가상 판결
    T3 : 대법원 최종 판결 (Anchor)

  핵심 가설:
    LCAM(T2) > LCAM(T1)   → K-Law가 원심보다 우수
    LCAM(T2) ≈ LCAM(T3)   → K-Law가 대법원 수준에 근접

입력 데이터 형식 (JSON):
  {
    "case_id": "2024다12345",
    "domain": "민사",
    "lower_court_text": "1심 또는 2심 판결 요약...",
    "case_summary": "사건 요약 (결과 제거)...",
    "supreme_court_text": "대법원 판결 요약..."
  }

입력:
  --input   : JSON 판례 디렉토리 (기본: ./summaries/2_법원비교_추가)
  --output  : 결과 CSV (기본: ./results/test_d_results.csv)
  --n       : 샘플 수 (기본: 40)
  --seed    : 랜덤 시드 (기본: 42)

실행:
  python experiments/test_d.py --input ./summaries/2_법원비교_추가 --n 40
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

import math

REPO_ROOT = Path(__file__).parent.parent

LCAM_AXES = {
    "A1_사실인정":   {"max": 20},
    "A2_법령적용":   {"max": 20},
    "A3_법리판단":   {"max": 20},
    "A4_증거판단":   {"max": 15},
    "A5_주문명확성": {"max": 15},
    "A6_이유설시":   {"max": 10},
}

def load_prompt(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    return p.read_text(encoding="utf-8") if p.exists() else ""

KLAW_SYSTEM  = load_prompt("klaw/prompts/system_prompt.txt")
LCAM_RUBRIC  = load_prompt("klaw/lcam/scoring_rubric.txt")
PLAIN_SYSTEM = load_prompt("klaw/prompts/plain_llm_prompt.txt")

# ---------------------------------------------------------------------------
# LCAM 채점
# ---------------------------------------------------------------------------
def build_scoring_prompt(text: str, role: str) -> str:
    axes_desc = "\n".join(
        f"  {k} (/{v['max']}점)"
        for k, v in LCAM_AXES.items()
    )
    return f"""다음 [{role}]을 LCAM 6축으로 채점하십시오.

[텍스트]
{text[:2500]}

[축]
{axes_desc}

JSON 형식으로만 응답:
{{
  "A1_사실인정": <정수>,
  "A2_법령적용": <정수>,
  "A3_법리판단": <정수>,
  "A4_증거판단": <정수>,
  "A5_주문명확성": <정수>,
  "A6_이유설시": <정수>
}}
"""

def score_text(
    client: Anthropic,
    text: str,
    role: str,
    system: str,
    model: str,
    retries: int = 3,
) -> Optional[dict]:
    prompt = build_scoring_prompt(text, role)
    for attempt in range(retries):
        try:
            kwargs = {
                "model": model, "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            resp = client.messages.create(**kwargs)
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            scores = json.loads(raw)
            for k, v in LCAM_AXES.items():
                scores[k] = max(0, min(v["max"], int(scores.get(k, 0))))
            scores["total"] = sum(scores[k] for k in LCAM_AXES)
            return scores
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"    [WARN] 채점 실패: {e}")
    return None

# ---------------------------------------------------------------------------
# K-Law 가상 판결 생성
# ---------------------------------------------------------------------------
def generate_klaw_judgment(client: Anthropic, case_summary: str, model: str) -> str:
    prompt = f"""다음 사건에 대한 K-Law 가상 판결을 작성하십시오.

[사건 요약]
{case_summary[:2000]}

판결 형식:
1. 주문
2. 이유 (사실인정 → 법령적용 → 법리판단 → 결론)
"""
    try:
        kwargs = {
            "model": model, "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
        }
        if KLAW_SYSTEM:
            kwargs["system"] = KLAW_SYSTEM
        resp = client.messages.create(**kwargs)
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"    [WARN] K-Law 판결 생성 실패: {e}")
        return ""

# ---------------------------------------------------------------------------
# 통계 유틸
# ---------------------------------------------------------------------------
def mean(lst):
    return sum(lst) / len(lst) if lst else float("nan")

def paired_t_stat(a_list, b_list):
    """단순 대응 t 통계량"""
    diffs = [a - b for a, b in zip(a_list, b_list)]
    n = len(diffs)
    if n < 2:
        return float("nan"), float("nan")
    d_mean = mean(diffs)
    s = math.sqrt(sum((d - d_mean) ** 2 for d in diffs) / (n - 1))
    if s == 0:
        return float("nan"), float("nan")
    t = d_mean / (s / math.sqrt(n))
    return t, d_mean

def cohens_d(a_list, b_list):
    """Cohen's d (효과 크기)"""
    if len(a_list) < 2:
        return float("nan")
    ma, mb = mean(a_list), mean(b_list)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a_list) / (len(a_list) - 1))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b_list) / (len(b_list) - 1))
    pooled = math.sqrt((sa ** 2 + sb ** 2) / 2)
    return (ma - mb) / pooled if pooled else float("nan")

# ---------------------------------------------------------------------------
# 판례 로드
# ---------------------------------------------------------------------------
def load_cases(input_dir: str, n: int, seed: int) -> list[dict]:
    p = Path(input_dir)
    files = sorted(p.glob("*.json"))
    random.seed(seed)
    random.shuffle(files)
    files = files[:n]

    cases = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # 필수 필드 확인
            required = ["case_id", "case_summary", "lower_court_text", "supreme_court_text"]
            if all(k in data for k in required):
                cases.append(data)
            else:
                print(f"  [WARN] {f.name}: 필수 필드 누락 {required}")
        except Exception as e:
            print(f"  [WARN] {f.name} 로드 실패: {e}")
    return cases

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Tripartite: 1·2심 vs K-Law vs 대법원")
    parser.add_argument("--input",  default="./summaries/2_법원비교_추가")
    parser.add_argument("--output", default="./results/test_d_results.csv")
    parser.add_argument("--n",      type=int, default=40)
    parser.add_argument("--seed",   type=int, default=42)
    parser.add_argument("--model",  default="claude-sonnet-4-20250514")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("[ERROR] ANTHROPIC_API_KEY 환경변수 필요")

    client = Anthropic(api_key=api_key)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(args.input, args.n, args.seed)
    if not cases:
        sys.exit(f"[ERROR] 판례 없음: {args.input}")

    print(f"[test_d] {len(cases)}건 로드 — 3판결 × {len(cases)}건 = {3*len(cases)} 채점")

    rows = []
    totals_lower  = []   # T1: 원심
    totals_klaw   = []   # T2: K-Law
    totals_supreme = []  # T3: 대법원

    for i, case in enumerate(cases, 1):
        cid = case["case_id"]
        print(f"  [{i:02d}/{len(cases)}] {cid}")

        # T1: 원심 채점
        s1 = score_text(client, case["lower_court_text"],
                        "1심/2심 판결", PLAIN_SYSTEM, args.model)
        time.sleep(0.3)

        # T2: K-Law 가상 판결 생성 후 채점
        klaw_text = generate_klaw_judgment(client, case["case_summary"], args.model)
        time.sleep(0.3)
        s2 = score_text(client, klaw_text, "K-Law 가상 판결",
                        KLAW_SYSTEM, args.model) if klaw_text else None
        time.sleep(0.3)

        # T3: 대법원 채점
        s3 = score_text(client, case["supreme_court_text"],
                        "대법원 판결", PLAIN_SYSTEM, args.model)
        time.sleep(0.3)

        if not (s1 and s2 and s3):
            print(f"    [SKIP] 채점 실패")
            continue

        row = {
            "case_id":  cid,
            "domain":   case.get("domain", ""),
            "total_lower":   s1["total"],
            "total_klaw":    s2["total"],
            "total_supreme": s3["total"],
            "klaw_vs_lower_diff":   s2["total"] - s1["total"],
            "klaw_vs_supreme_diff": s2["total"] - s3["total"],
        }
        for ax in LCAM_AXES:
            row[f"{ax}_lower"]   = s1[ax]
            row[f"{ax}_klaw"]    = s2[ax]
            row[f"{ax}_supreme"] = s3[ax]

        rows.append(row)
        totals_lower.append(s1["total"])
        totals_klaw.append(s2["total"])
        totals_supreme.append(s3["total"])

    if not rows:
        sys.exit("[ERROR] 유효한 결과 없음")

    # --- 통계 ---
    t_kl, d_kl = paired_t_stat(totals_klaw, totals_lower)
    t_ks, d_ks = paired_t_stat(totals_klaw, totals_supreme)
    cd_kl = cohens_d(totals_klaw, totals_lower)
    cd_ks = cohens_d(totals_klaw, totals_supreme)

    print("\n[test_d] ===== 결과 요약 =====")
    print(f"  평균 LCAM — 원심: {mean(totals_lower):.1f}, "
          f"K-Law: {mean(totals_klaw):.1f}, "
          f"대법원: {mean(totals_supreme):.1f}")
    print(f"  K-Law vs 원심  — t={t_kl:.3f}, 평균차={d_kl:.2f}, d={cd_kl:.3f}")
    print(f"  K-Law vs 대법원 — t={t_ks:.3f}, 평균차={d_ks:.2f}, d={cd_ks:.3f}")

    win_lower   = sum(1 for a, b in zip(totals_klaw, totals_lower)   if a > b)
    win_supreme = sum(1 for a, b in zip(totals_klaw, totals_supreme) if a >= b - 5)
    print(f"  K-Law > 원심: {win_lower}/{len(rows)} ({100*win_lower/len(rows):.1f}%)")
    print(f"  K-Law ≈ 대법원 (±5): {win_supreme}/{len(rows)} ({100*win_supreme/len(rows):.1f}%)")

    # --- CSV ---
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # --- 요약 JSON ---
    summary = {
        "n": len(rows),
        "mean_lower":   round(mean(totals_lower), 2),
        "mean_klaw":    round(mean(totals_klaw), 2),
        "mean_supreme": round(mean(totals_supreme), 2),
        "t_klaw_vs_lower":   round(t_kl, 4),
        "t_klaw_vs_supreme": round(t_ks, 4),
        "cohens_d_klaw_vs_lower":   round(cd_kl, 4),
        "cohens_d_klaw_vs_supreme": round(cd_ks, 4),
        "klaw_beats_lower_pct":   round(100 * win_lower / len(rows), 1),
        "klaw_near_supreme_pct":  round(100 * win_supreme / len(rows), 1),
    }
    sj = Path(args.output).with_suffix(".summary.json")
    sj.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[test_d] 결과 저장: {args.output}")
    print(f"[test_d] 요약 저장: {sj}")
    print("[test_d] 완료")

if __name__ == "__main__":
    main()
