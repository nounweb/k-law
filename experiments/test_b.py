#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test B: K-Law vs Plain LLM 3종 비교
- Claude 3.5 Sonnet, DeepSeek-R1, Gemini 1.5 Pro
- 동일 프롬프트, K-Law 방법론 없이 순수 추론
- ΔOA = OA_KLaw - OA_PlainLLM 측정
"""

import os
import csv
import time
import pathlib
import anthropic
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

INPUT_DIR  = "paper_data/2_KLaw_실험"
OUTPUT_DIR = "results"
DELAY      = 1.5

# ── Plain LLM 공통 프롬프트 (3종 동일) ──
with open("klaw/prompts/plain_llm_prompt.txt", encoding="utf-8") as f:
    PLAIN_PROMPT = f.read()

# ── 클라이언트 초기화 ──
openai_client    = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-pro")


def call_claude(summary: str) -> str | None:
    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=[{"role": "user", "content": PLAIN_PROMPT.format(summary=summary)}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  [Claude 오류] {e}")
        return None


def call_deepseek(summary: str) -> str | None:
    try:
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        resp = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": PLAIN_PROMPT.format(summary=summary)}],
            max_tokens=1500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [DeepSeek 오류] {e}")
        return None


def call_gemini(summary: str) -> str | None:
    try:
        resp = gemini_model.generate_content(PLAIN_PROMPT.format(summary=summary))
        return resp.text.strip()
    except Exception as e:
        print(f"  [Gemini 오류] {e}")
        return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = sorted(pathlib.Path(INPUT_DIR).glob("*_요약.txt"))
    print(f"대상 파일: {len(files)}건 × 3종 모델\n")

    rows = []
    for idx, fpath in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] {fpath.name[:50]}")
        summary = fpath.read_text(encoding="utf-8")

        claude_r   = call_claude(summary);   time.sleep(DELAY)
        deepseek_r = call_deepseek(summary); time.sleep(DELAY)
        gemini_r   = call_gemini(summary);   time.sleep(DELAY)

        rows.append({
            "file":     fpath.name,
            "claude":   claude_r   or "FAIL",
            "deepseek": deepseek_r or "FAIL",
            "gemini":   gemini_r   or "FAIL",
        })
        print(f"  Claude: {'✔' if claude_r else '✘'}  "
              f"DeepSeek: {'✔' if deepseek_r else '✘'}  "
              f"Gemini: {'✔' if gemini_r else '✘'}")

    out = os.path.join(OUTPUT_DIR, "test_b_plain_llm.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file","claude","deepseek","gemini"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
