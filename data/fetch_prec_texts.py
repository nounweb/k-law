#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
법제처 판례 본문(판결문) 수집기
- prec_list_1008.json 에서 판례일련번호를 읽어 XML API로 본문 수집
- 저장 폴더: C:/Users/주피터/Downloads/1008_cases
- 국세법령정보시스템 출처는 자동 제외 (XML API 미지원)
- 중단 후 재시작 시 이미 저장된 파일은 자동으로 건너뜀
"""

import requests
import json
import os
import time
import re
import xml.etree.ElementTree as ET

# ────────────── 설정 ──────────────
OC         = "openhash"
INPUT_JSON = "C:/Users/주피터/Downloads/1008_cases/prec_list_1008.json"
SAVE_DIR   = "C:/Users/주피터/Downloads/1008_cases"
DELAY      = 0.8

os.makedirs(SAVE_DIR, exist_ok=True)


# ────────────── XML 전체 텍스트 추출 ──────────────
def _elem_to_text(elem) -> str:
    texts = []
    if elem.text and elem.text.strip():
        texts.append(elem.text.strip())
    for child in elem:
        child_text = _elem_to_text(child)
        if child_text:
            texts.append(child_text)
        if child.tail and child.tail.strip():
            texts.append(child.tail.strip())
    return "\n".join(texts)


def fetch_detail_xml(prec_id: str) -> str | None:
    """판례일련번호로 판결문 본문 수집"""
    url = "http://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC":     OC,
        "target": "prec",
        "type":   "XML",
        "ID":     prec_id,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠ 요청 실패: {e}")
        return None

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None

    text = _elem_to_text(root).strip()
    return text if len(text) > 50 else None


# ────────────── 메인 ──────────────
def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        prec_list = json.load(f)

    total   = len(prec_list)
    success = 0
    skipped = 0
    fail_log = []

    print(f"총 {total}건 판결문 수집 시작\n")

    for idx, prec in enumerate(prec_list, 1):
        prec_id   = prec.get("판례일련번호", "")
        domain    = prec.get("분야", "기타")
        case_name = prec.get("사건명", "사건명없음")[:50]
        source    = prec.get("데이터출처명", "")

        # 국세법령정보시스템 출처 제외 (XML API 미지원)
        if source == "국세법령정보시스템":
            print(f"[{idx}/{total}] 건너뜀(국세): {case_name[:30]}")
            fail_log.append(prec_id)
            continue

        if not prec_id:
            print(f"[{idx}/{total}] ✘ ID 없음")
            fail_log.append("UNKNOWN")
            continue

        safe_name = re.sub(r'[\\/*?:"<>|]', "_", case_name)
        filename  = f"{domain}_{prec_id}_{safe_name}.txt"
        filepath  = os.path.join(SAVE_DIR, filename)

        # 이미 저장된 파일 건너뜀 (재시작 시 이어받기)
        if os.path.exists(filepath):
            print(f"[{idx}/{total}] ✔ 기존 파일: {filename[:40]}")
            success += 1
            skipped += 1
            continue

        print(f"[{idx}/{total}] [{domain}] {prec_id} - {case_name[:25]}...", end=" ", flush=True)

        text = fetch_detail_xml(prec_id)
        if text:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✔ ({len(text):,}자)")
            success += 1
        else:
            print("✘ 본문 없음")
            fail_log.append(prec_id)

        time.sleep(DELAY)

    # ── 최종 결과 ──
    print("\n" + "=" * 55)
    print(f"완료:     {success}건 (신규 {success - skipped}건 + 기존 {skipped}건)")
    print(f"실패:     {len(fail_log)}건")
    print(f"저장 폴더: {SAVE_DIR}")
    if fail_log:
        print(f"실패 ID: {fail_log}")


if __name__ == "__main__":
    main()
