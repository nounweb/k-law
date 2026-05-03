#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLAS 실험 결과 통계 분석
- 대응 표본 t검정 (K-Law vs 법원)
- Cohen's d 효과 크기
- Cohen's κ (평가자 간 신뢰도)
- ΔOA (방법론 부가가치)
"""

import pandas as pd
import numpy as np
from scipy import stats
import krippendorff
import warnings
warnings.filterwarnings("ignore")


def cohens_d(x, y):
    """대응 표본 Cohen's d"""
    diff = np.array(x) - np.array(y)
    return diff.mean() / diff.std(ddof=1)


def cohens_kappa(r1, r2):
    """Cohen's κ (이진 또는 다범주)"""
    from sklearn.metrics import cohen_kappa_score
    return cohen_kappa_score(r1, r2)


def analyze_test_a(filepath: str):
    """Test A: K-Law vs 법원 LCAM 점수 비교"""
    print("\n" + "="*60)
    print("Test A: K-Law vs 법원 판결 법리 완전성 비교")
    print("="*60)

    df = pd.read_csv(filepath)
    klaw_scores  = df["klaw_lcam_score"].dropna()
    court_scores = df["court_lcam_score"].dropna()

    # 대응 표본 t검정
    t_stat, p_val = stats.ttest_rel(klaw_scores, court_scores, alternative="greater")
    d = cohens_d(klaw_scores, court_scores)
    ci = stats.t.interval(0.95, len(klaw_scores)-1,
                          loc=np.mean(klaw_scores - court_scores),
                          scale=stats.sem(klaw_scores - court_scores))

    print(f"K-Law 평균: {klaw_scores.mean():.2f} (SD={klaw_scores.std():.2f})")
    print(f"법원 평균:  {court_scores.mean():.2f} (SD={court_scores.std():.2f})")
    print(f"차이:       {(klaw_scores-court_scores).mean():.2f}점")
    print(f"t통계량:    {t_stat:.3f}")
    print(f"p값:        {p_val:.4f} {'★ 유의' if p_val < 0.05 else '비유의'}")
    print(f"Cohen's d:  {d:.3f} ({'large' if abs(d)>0.8 else 'medium' if abs(d)>0.5 else 'small'})")
    print(f"95% CI:     [{ci[0]:.2f}, {ci[1]:.2f}]")

    # OA 비교
    if "klaw_oa" in df.columns and "court_oa" in df.columns:
        klaw_oa  = df["klaw_oa"].mean()
        court_oa = df["court_oa"].mean()
        print(f"\nK-Law OA:   {klaw_oa:.1%}")
        print(f"법원 OA:    {court_oa:.1%}")
        print(f"차이:       {klaw_oa - court_oa:+.1%}")


def analyze_test_b(filepath: str):
    """Test B: K-Law vs Plain LLM 3종 ΔOA"""
    print("\n" + "="*60)
    print("Test B: K-Law vs Plain LLM 방법론 부가가치 (ΔOA)")
    print("="*60)

    df = pd.read_csv(filepath)
    klaw_oa     = df["klaw_oa"].mean()
    claude_oa   = df["claude_oa"].mean()
    deepseek_oa = df["deepseek_oa"].mean()
    gemini_oa   = df["gemini_oa"].mean()
    plain_avg   = (claude_oa + deepseek_oa + gemini_oa) / 3

    print(f"K-Law OA:     {klaw_oa:.1%}")
    print(f"Claude OA:    {claude_oa:.1%}  ΔOA: {klaw_oa-claude_oa:+.1%}")
    print(f"DeepSeek OA:  {deepseek_oa:.1%}  ΔOA: {klaw_oa-deepseek_oa:+.1%}")
    print(f"Gemini OA:    {gemini_oa:.1%}  ΔOA: {klaw_oa-gemini_oa:+.1%}")
    print(f"Plain 평균:   {plain_avg:.1%}  ΔOA_avg: {klaw_oa-plain_avg:+.1%}")
    print(f"\n방법론 부가가치: {klaw_oa-plain_avg:+.1%}p")


def analyze_test_c(filepath: str):
    """Test C: LCAM 평가자 간 신뢰도 (Cohen's κ)"""
    print("\n" + "="*60)
    print("Test C: LCAM 평가자 간 신뢰도 (Cohen's κ)")
    print("="*60)

    df = pd.read_csv(filepath)
    pairs = [("rater1","rater2"), ("rater1","rater3"), ("rater2","rater3")]
    kappas = []
    for r1, r2 in pairs:
        if r1 in df.columns and r2 in df.columns:
            k = cohens_kappa(df[r1].dropna(), df[r2].dropna())
            kappas.append(k)
            label = "substantial" if k>=0.61 else "moderate" if k>=0.41 else "fair"
            print(f"κ ({r1}-{r2}): {k:.3f} [{label}]")

    if kappas:
        avg_k = np.mean(kappas)
        print(f"\n평균 κ: {avg_k:.3f}")
        print(f"기준(0.61) {'✔ 달성' if avg_k >= 0.61 else '✘ 미달성'}")


def main():
    import sys
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"

    import os
    for test, func in [
        ("test_a_lcam.csv",    analyze_test_a),
        ("test_b_oa.csv",      analyze_test_b),
        ("test_c_kappa.csv",   analyze_test_c),
    ]:
        path = os.path.join(results_dir, test)
        if os.path.exists(path):
            func(path)
        else:
            print(f"\n[건너뜀] {test} 없음")

    print("\n\n분석 완료.")


if __name__ == "__main__":
    main()
