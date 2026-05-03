#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
논문 1·2·3 데이터 분할 스크립트 (split_final.py)
- 입력: C:/Users/주피터/Downloads/1008_cases/*.txt
- 출력: C:/Users/주피터/Downloads/paper_data/

폴더별 목표:
  0_예비          여유분 (~158건)
  1_이론방법론    60건  (전원합의체 자동 필터 + 분야별 균등)
  2_KLaw_실험     200건 (7개 분야 층화 추출)
  2_PlainLLM_결과 빈 폴더
  2_Anchor_Set    100건
  2_법원비교_추가  40건
  3_시스템응용    250건
"""

import os
import shutil
import random
from collections import defaultdict

# ────────────── 설정 ──────────────
SRC  = "C:/Users/주피터/Downloads/1008_cases"
DEST = "C:/Users/주피터/Downloads/paper_data"
RANDOM_SEED = 42

FOLDERS = [
    "0_예비",
    "1_이론방법론",
    "2_KLaw_실험",
    "2_PlainLLM_결과",
    "2_Anchor_Set",
    "2_법원비교_추가",
    "3_시스템응용",
]

# 7개 분야 (파일명 접두어 기준)
DOMAINS = ["민사", "형사", "행정", "노동", "가사", "지식재산", "회사"]

# 논문2 K-Law 실험 분야별 목표 건수 (합계 200건)
KLAW_QUOTA = {
    "민사":    60,
    "형사":    40,
    "행정":    35,
    "노동":    30,
    "가사":    15,
    "지식재산": 12,
    "회사":     8,
}  # 합계 200

# 논문2 Anchor Set 분야별 목표 건수 (합계 100건)
ANCHOR_QUOTA = {
    "민사":    30,
    "형사":    20,
    "행정":    18,
    "노동":    15,
    "가사":     8,
    "지식재산":  6,
    "회사":     3,
}  # 합계 100

# 3_시스템응용 관련 키워드 (파일명 또는 분야)
SYS_DOMAINS = ["지식재산", "회사"]
SYS_KEYWORDS = [
    "임대차", "개인정보", "특허", "상표", "디자인", "저작권",
    "하도급", "약관", "공정거래", "소비자", "계약", "매매",
    "부당이득", "과징금", "물품대금",
]

# ────────────── 초기화 ──────────────
def setup():
    random.seed(RANDOM_SEED)
    for folder in FOLDERS:
        os.makedirs(os.path.join(DEST, folder), exist_ok=True)
    print(f"폴더 생성 완료: {DEST}\n")

# ────────────── 파일 수집 및 분류 ──────────────
def collect_files():
    """SRC의 모든 txt를 분야별로 분류"""
    all_files = [f for f in os.listdir(SRC) if f.endswith(".txt")]
    by_domain = defaultdict(list)
    unclassified = []

    for f in all_files:
        matched = False
        for domain in DOMAINS:
            if f.startswith(domain + "_"):
                by_domain[domain].append(f)
                matched = True
                break
        if not matched:
            unclassified.append(f)

    print(f"전체 파일: {len(all_files)}건")
    for d in DOMAINS:
        print(f"  {d}: {len(by_domain[d])}건")
    print(f"  분류불가: {len(unclassified)}건\n")

    # 각 분야 내부 셔플
    for d in DOMAINS:
        random.shuffle(by_domain[d])
    random.shuffle(unclassified)

    return all_files, by_domain, unclassified

# ────────────── 복사 헬퍼 ──────────────
def copy_files(file_list, folder, used):
    folder_path = os.path.join(DEST, folder)
    count = 0
    for f in file_list:
        if f in used:
            continue
        shutil.copy(os.path.join(SRC, f), os.path.join(folder_path, f))
        used.add(f)
        count += 1
    return count

# ────────────── 층화 추출 헬퍼 ──────────────
def stratified_sample(by_domain, quota, used):
    selected = []
    for domain, n in quota.items():
        candidates = [f for f in by_domain[domain] if f not in used]
        n = min(n, len(candidates))
        chosen = random.sample(candidates, n)
        selected.extend(chosen)
    return selected

# ────────────── 메인 분할 ──────────────
def split():
    setup()
    all_files, by_domain, unclassified = collect_files()
    used = set()

    # ── 1. 논문1 (1_이론방법론): 60건 ──────────────────────
    # 전원합의체 자동 필터
    en_banc = [f for f in all_files if "전원합의체" in f]
    chosen_p1 = list(en_banc[:min(60, len(en_banc))])
    print(f"전원합의체: {len(en_banc)}건 → {len(chosen_p1)}건 선택")

    # 부족분 분야별 균등 보충
    need = 60 - len(chosen_p1)
    if need > 0:
        per_domain = need // len(DOMAINS)
        remainder = need % len(DOMAINS)
        for i, domain in enumerate(DOMAINS):
            quota = per_domain + (1 if i < remainder else 0)
            candidates = [f for f in by_domain[domain]
                          if f not in used and f not in chosen_p1]
            chosen_p1.extend(random.sample(candidates, min(quota, len(candidates))))

    chosen_p1 = list(dict.fromkeys(chosen_p1))[:60]  # 중복 제거 후 60건 확정
    cnt = copy_files(chosen_p1, "1_이론방법론", used)
    print(f"1_이론방법론: {cnt}건\n")

    # ── 2. 논문2 K-Law 실험 (2_KLaw_실험): 200건 ──────────────
    klaw_files = stratified_sample(by_domain, KLAW_QUOTA, used)
    # 부족분 unclassified로 보충
    if len(klaw_files) < 200:
        short = 200 - len(klaw_files)
        extra = [f for f in unclassified if f not in used][:short]
        klaw_files.extend(extra)
    cnt = copy_files(klaw_files, "2_KLaw_실험", used)
    print(f"2_KLaw_실험: {cnt}건\n")

    # ── 3. Anchor Set (2_Anchor_Set): 100건 ──────────────────
    anchor_files = stratified_sample(by_domain, ANCHOR_QUOTA, used)
    if len(anchor_files) < 100:
        short = 100 - len(anchor_files)
        extra = [f for f in unclassified if f not in used][:short]
        anchor_files.extend(extra)
    cnt = copy_files(anchor_files, "2_Anchor_Set", used)
    print(f"2_Anchor_Set: {cnt}건\n")

    # ── 4. 법원비교 추가 (2_법원비교_추가): 40건 ──────────────
    remaining = [f for f in all_files if f not in used]
    extra_40 = random.sample(remaining, min(40, len(remaining)))
    cnt = copy_files(extra_40, "2_법원비교_추가", used)
    print(f"2_법원비교_추가: {cnt}건\n")

    # ── 5. 논문3 시스템응용 (3_시스템응용): 250건 ─────────────
    # 파일명 키워드 기반 우선 선택
    sys_candidates = []
    for f in all_files:
        if f in used:
            continue
        domain_match = any(f.startswith(d + "_") for d in SYS_DOMAINS)
        keyword_match = any(kw in f for kw in SYS_KEYWORDS)
        if domain_match or keyword_match:
            sys_candidates.append(f)

    sys_files = random.sample(sys_candidates, min(250, len(sys_candidates)))

    # 부족분 나머지에서 보충
    if len(sys_files) < 250:
        short = 250 - len(sys_files)
        fallback = [f for f in all_files
                    if f not in used and f not in sys_files]
        sys_files.extend(random.sample(fallback, min(short, len(fallback))))

    cnt = copy_files(sys_files, "3_시스템응용", used)
    print(f"3_시스템응용: {cnt}건\n")

    # ── 6. 나머지 → 0_예비 ───────────────────────────────────
    leftover = [f for f in all_files if f not in used]
    cnt = copy_files(leftover, "0_예비", used)
    print(f"0_예비: {cnt}건\n")

    # ── 최종 집계 ─────────────────────────────────────────────
    print("=" * 50)
    print("최종 분할 결과")
    print("=" * 50)
    total = 0
    for folder in FOLDERS:
        path = os.path.join(DEST, folder)
        n = len([f for f in os.listdir(path) if f.endswith(".txt")])
        total += n
        print(f"  {folder:<20}: {n:>4}건")
    print(f"  {'합계':<20}: {total:>4}건")
    print(f"\n저장 위치: {DEST}")

if __name__ == "__main__":
    split()
