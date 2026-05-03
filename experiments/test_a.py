#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test A: K-Law 가상 판결 vs 실제 대법원 판결 비교
- LCAM 법리 완전성 점수 비교
- 판결 방향 일치율 (OA) 측정
- 입력: 2_KLaw_실험 폴더의 요약본 (판결 결과 제거)
- 출력: results/test_a_results.csv
"""

import os
import json
import csv
import time
import pathlib
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INPUT_DIR  = "paper_data/2_KLaw_실험"
OUTPUT_DIR = "results"
MODEL      = "gpt-4o-mini"
DELAY      = 1.5

# ── K-Law 시스템 프롬프트 로드 ──
with open("klaw/prompts/system_prompt.txt", encoding="utf-8") as f:
    KLAW_SYSTEM = f.read()

with open("klaw/prompts/reverse_reasoning.txt", encoding="utf-8") as f:
    REVERSE_REASONING = f.read()

KLAW_USER = """다음 사건 요약본을 바탕으로 K-Law 방법론(15개 공리, 역방향 추론)을
적용하여 가상 판결을 생성하시오.

출력 형식:
1. 판결 방향: [원고 승소 / 피고 승소 / 일부 인용]
2. 핵심 법리 논거: (공리 적용 내역 포함)
3. 확신도: [0~10]
4. Hard Case 여부: [예 / 아니오] (확신도 < 4이면 예)

[사건 요약]
{summary}"""


def generate_klaw_judgment(summary: str) -> dict | None:
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": KLAW_SYSTEM + "\n\n" + REVERSE_REASONING},
                {"role": "user",   "content": KLAW_USER.format(summary=summary)},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        return {"result": resp.choices[0].message.content.strip()}
    except Exception as e:
        print(f"  [오류] {e}")
        return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = sorted(pathlib.Path(INPUT_DIR).glob("*_요약.txt"))
    print(f"대상 파일: {len(files)}건\n")

    rows = []
    for idx, fpath in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] {fpath.name[:50]}")
        summary = fpath.read_text(encoding="utf-8")
        result = generate_klaw_judgment(summary)
        if result:
            rows.append({
                "file": fpath.name,
                "klaw_judgment": result["result"],
                "status": "success",
            })
            print(f"  ✔ 완료")
        else:
            rows.append({"file": fpath.name, "klaw_judgment": "", "status": "fail"})
            print(f"  ✘ 실패")
        time.sleep(DELAY)

    out = os.path.join(OUTPUT_DIR, "test_a_klaw_judgments.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "klaw_judgment", "status"])
        writer.writeheader()
        writer.writerows(rows)

    success = sum(1 for r in rows if r["status"] == "success")
    print(f"\n완료: {success}/{len(files)}건 → {out}")


if __name__ == "__main__":
    main()
