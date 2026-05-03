#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
판례 1008건 전체 요약 (6개 항목)
- 모델: gpt-4o-mini
- 진행상황 저장 → 중단 후 재개 가능
- 700자 미만 시 재작성 1회, 재시도 후에도 미달 시 저장 안 함
- 입력: C:/Users/주피터/Downloads/1008_cases/*.txt
- 출력: C:/Users/주피터/Downloads/1008_cases/summary/
- 진행상황: C:/Users/주피터/Downloads/1008_cases/summary/progress.json
"""

import time
import json
import pathlib
from datetime import datetime
from openai import OpenAI

# ────────────── 설정 ──────────────
API_KEY = "키를 입력하세요"
SOURCE_DIR  = "C:/Users/주피터/Downloads/1008_cases"
OUTPUT_DIR  = "C:/Users/주피터/Downloads/1008_cases/summary"
PROGRESS_FILE = "C:/Users/주피터/Downloads/1008_cases/summary/progress.json"
MODEL       = "gpt-4o-mini"
MIN_LENGTH  = 700
REQUEST_DELAY = 1.5   # 초 (분당 약 40건, rate limit 여유)
MAX_RETRIES = 3       # API 오류 시 재시도 횟수

client = OpenAI(api_key=API_KEY)

# ────────────── 프롬프트 ──────────────
SYSTEM_PROMPT = """당신은 대한민국 법원 판결문을 분석하는 법률 전문가입니다.
다음 규칙을 반드시 준수하십시오.
1. 판결 결과(인용·기각·파기·환송·상고기각 등)를 절대 언급하지 마십시오.
2. 판결을 암시하는 표현(예: "법원은 ~라고 판단하였다", "원심은 ~를 인정하였다")도 금지입니다.
3. 각 항목은 구체적 사실(날짜·금액·법령·행위)을 포함하여 충분히 상세하게 작성하십시오."""

USER_PROMPT = """다음 판결문을 아래 6개 항목으로 정리하십시오.
판결 결과나 판결을 암시하는 내용은 절대 포함하지 마십시오.
각 항목은 반드시 구체적이고 충분한 분량으로 작성하십시오.

## 1. 사건의 개요
- 당사자 관계, 사건 경위(시간 순서), 소송의 발단을 구체적으로 서술

## 2. 원고의 주장
- 청구 내용, 법적 근거(조문 포함), 사실적 논거를 구체적으로 서술

## 3. 피고의 주장
- 반박 내용, 법적 근거, 사실적 논거를 구체적으로 서술

## 4. 다툼이 없는 사실
- 양측이 공통으로 인정하는 사실관계(날짜·금액·계약 내용 등 구체적 수치 포함)

## 5. 다툼의 내용
- 양측이 서로 다르게 주장하는 사실관계 및 법리적 쟁점을 항목별로 서술

## 6. 판결해야 할 사항 및 법리
- 법원이 판단해야 할 핵심 쟁점과 적용될 법리·판례를 구체적으로 서술

[판결문]
{text}"""

RETRY_PROMPT = """이전 답변의 분량이 부족합니다. 아래 6개 항목 전체를 더 상세하게 재작성하십시오.
각 항목마다 구체적인 날짜·금액·법령·행위를 포함하여 충분한 분량으로 작성하십시오.
판결 결과는 절대 포함하지 마십시오.

## 1. 사건의 개요
## 2. 원고의 주장
## 3. 피고의 주장
## 4. 다툼이 없는 사실
## 5. 다툼의 내용
## 6. 판결해야 할 사항 및 법리

[판결문]
{text}"""

# ────────────── 전처리 ──────────────
def preprocess(text: str) -> str:
    skip_keywords = ["주문", "파기환송", "상고기각", "원심파기", "원심판결을 파기"]
    lines = []
    for line in text.splitlines():
        if any(kw in line for kw in skip_keywords):
            continue
        lines.append(line)
    return "\n".join(lines)[:60000]

# ────────────── API 호출 (재시도 포함) ──────────────
def call_api(text: str, is_retry: bool = False) -> str | None:
    template = RETRY_PROMPT if is_retry else USER_PROMPT
    user_content = template.format(text=text)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            wait = (attempt + 1) * 10
            print(f"  [API 오류] {e} → {wait}초 후 재시도 ({attempt+1}/{MAX_RETRIES})")
            time.sleep(wait)
    return None

# ────────────── 진행상황 저장·로드 ──────────────
def load_progress() -> set:
    p = pathlib.Path(PROGRESS_FILE)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("completed", []))
    return set()

def save_progress(completed: set, stats: dict):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "completed": list(completed),
            "stats": stats,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, f, ensure_ascii=False, indent=2)

# ────────────── 메인 ──────────────
def main():
    src_dir = pathlib.Path(SOURCE_DIR)
    out_dir = pathlib.Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    # summary 폴더 내 txt 제외하고 원본만 수집
    files = sorted([
        f for f in src_dir.glob("*.txt")
    ])

    if not files:
        print(f"[오류] {SOURCE_DIR} 에 txt 파일이 없습니다.")
        return

    # 진행상황 로드
    completed = load_progress()
    remaining = [f for f in files if f.stem not in completed]

    total = len(files)
    print(f"전체: {total}건 | 완료: {len(completed)}건 | 남은 건: {len(remaining)}건")
    print(f"출력 폴더: {OUTPUT_DIR}\n")

    success = len(completed)
    fail = 0
    disqualified = 0

    for idx, fpath in enumerate(remaining, 1):
        elapsed_idx = len(completed) + idx
        print(f"[{elapsed_idx}/{total}] {fpath.name[:60]}")

        try:
            raw = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  [파일 읽기 오류] {e}\n")
            fail += 1
            continue

        text = preprocess(raw)

        # 1차 시도
        result = call_api(text, is_retry=False)
        if result is None:
            print(f"  [실패] API 오류\n")
            fail += 1
            continue

        print(f"  1차: {len(result)}자")

        # 700자 미만 → 재시도
        if len(result) < MIN_LENGTH:
            print(f"  [실격] {len(result)}자 < {MIN_LENGTH}자 → 재작성...")
            time.sleep(3)
            result = call_api(text, is_retry=True)
            if result is None:
                print(f"  [실패] 재시도 API 오류\n")
                fail += 1
                continue
            print(f"  재시도: {len(result)}자")
            if len(result) < MIN_LENGTH:
                print(f"  [최종 실격] → 저장 안 함\n")
                disqualified += 1
                continue

        # 저장
        out_path = out_dir / f"{fpath.stem}_요약.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"원본 파일: {fpath.name}\n")
            f.write(f"글자 수: {len(result)}자\n")
            f.write(f"처리 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(result)

        print(f"  ✔ 저장 ({len(result)}자)\n")
        success += 1
        completed.add(fpath.stem)

        # 진행상황 저장 (매 건마다)
        save_progress(completed, {
            "success": success,
            "fail": fail,
            "disqualified": disqualified,
        })

        time.sleep(REQUEST_DELAY)

    # 최종 결과
    print("=" * 50)
    print(f"완료: {success}건 | 실패: {fail}건 | 실격: {disqualified}건")
    print(f"저장 폴더: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
