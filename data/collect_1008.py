"""
법제처 판례 1008건 수집 & 판결문 저장 (통합본 v4)
- 분야별 중요도 기반 배분 수집
- 국세법령정보시스템 출처 판례 제외
- 전체 텍스트 추출 방식
- 저장 폴더: C:/Users/주피터/Downloads/1008_cases

분야별 배분:
  민사   350건 (손해배상·임대차·계약·부동산 등)
  형사   200건 (사기·횡령·폭행·마약 등)
  행정   150건 (행정처분·조세·국가배상 등)
  노동   150건 (해고·임금·산재·부당노동행위 등)
  가사    60건 (이혼·상속·친권·재산분할 등)
  지식재산 50건 (특허·상표·저작권·영업비밀 등)
  회사    48건 (주주총회·합병·이사·신주발행 등)
  합계  1008건
"""

import requests
import json
import os
import time
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime

# ────────────── 설정 ──────────────
OC = "openhash"
SAVE_DIR = "C:/Users/주피터/Downloads/1008_cases"
PER_PAGE = 100
REQUEST_DELAY = 0.6
TEXT_DELAY = 0.8

# 분야별 검색어 및 목표 건수
DOMAIN_QUERIES = [
    # (분야명, 목표건수, [검색어 목록])
    ("민사", 350, [
        "손해배상", "임대차보증금", "공사대금", "보험금", "부당이득",
        "구상금", "대여금", "약정금", "어음금", "소유권이전",
        "사해행위취소", "근저당권", "전세금", "매매대금", "보증채무",
    ]),
    ("형사", 200, [
        "사기", "횡령", "배임", "절도", "폭행",
        "성폭력", "뇌물", "명예훼손", "무고", "마약",
        "강도", "위증", "도로교통법위반", "개인정보보호법위반",
    ]),
    ("행정", 150, [
        "행정처분취소", "국가배상", "도시계획", "건축허가", "과징금",
        "증여세", "법인세", "부가가치세", "양도소득세", "취득세",
        "영업허가취소", "과태료", "정보공개",
    ]),
    ("노동", 150, [
        "부당해고", "임금체불", "퇴직금", "산업재해", "최저임금",
        "근로자지위확인", "부당노동행위", "직장내괴롭힘",
        "단체협약", "쟁의행위",
    ]),
    ("가사", 60, [
        "이혼", "친권", "상속회복", "유류분", "재산분할", "양육비",
    ]),
    ("지식재산", 50, [
        "특허침해", "상표권침해", "저작권침해", "영업비밀", "부정경쟁방지",
        "디자인권",
    ]),
    ("회사", 48, [
        "주주총회결의취소", "합병무효", "주식매수청구", "이사책임", "신주발행무효",
        "회사분할",
    ]),
]

# ────────────── 폴더 초기화 ──────────────
def reset_save_dir():
    if os.path.exists(SAVE_DIR):
        shutil.rmtree(SAVE_DIR)
        print(f"기존 폴더 삭제: {SAVE_DIR}")
    os.makedirs(SAVE_DIR)
    print(f"새 폴더 생성: {SAVE_DIR}\n")

# ────────────── 판례 목록 수집 ──────────────
def fetch_prec_list(query: str, page: int) -> list:
    url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": OC,
        "target": "prec",
        "type": "JSON",
        "search": 2,
        "query": query,
        "display": PER_PAGE,
        "page": page,
        "sort": "ddes",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("PrecSearch", {}).get("prec", [])
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []

def is_valid_prec(prec: dict) -> bool:
    name = prec.get("사건명", "")
    date_val = prec.get("선고일자", "")
    if not name or not date_val:
        return False
    if prec.get("데이터출처명") == "국세법령정보시스템":
        return False
    today_str = datetime.now().strftime("%Y%m%d")
    date_str = date_val.replace(".", "")
    if len(date_str) == 8 and date_str > today_str:
        return False
    if len(name) < 4:
        return False
    if not any('가' <= c <= '힣' for c in name):
        return False
    return True

def collect_domain(domain: str, target: int, queries: list, seen_ids: set) -> list:
    """한 분야의 판례를 target건 수집"""
    collected = []
    per_query = max(1, -(-target // len(queries)))  # 올림 나눗셈

    for query in queries:
        if len(collected) >= target:
            break
        query_count = 0
        for page in range(1, 6):
            if len(collected) >= target or query_count >= per_query:
                break
            prec_list = fetch_prec_list(query, page)
            if not prec_list:
                break
            added = 0
            for prec in prec_list:
                if len(collected) >= target or query_count >= per_query:
                    break
                prec_id = prec.get("판례일련번호", "")
                if is_valid_prec(prec) and prec_id not in seen_ids:
                    seen_ids.add(prec_id)
                    prec["분야"] = domain
                    collected.append(prec)
                    query_count += 1
                    added += 1
            print(f"  [{domain}] '{query}' p{page}: {added}건 추가 (분야누적: {len(collected)}/{target})")
            time.sleep(REQUEST_DELAY)

    return collected

def collect_all() -> list:
    all_prec = []
    seen_ids = set()
    for domain, target, queries in DOMAIN_QUERIES:
        print(f"\n{'='*50}")
        print(f"[{domain}] 목표: {target}건, 검색어: {len(queries)}개")
        domain_prec = collect_domain(domain, target, queries, seen_ids)
        all_prec.extend(domain_prec)
        print(f"[{domain}] 수집 완료: {len(domain_prec)}건 | 전체 누적: {len(all_prec)}건")
    return all_prec

# ────────────── 판결문 본문 수집 ──────────────
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
    url = "http://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": OC,
        "target": "prec",
        "type": "XML",
        "ID": prec_id,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception:
        return None
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None
    text = _elem_to_text(root).strip()
    return text if len(text) > 50 else None

def save_text(filename: str, text: str):
    path = os.path.join(SAVE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

# ────────────── 메인 ──────────────
def main():
    print("=" * 50)
    print("판례 1008건 수집 시작 (분야별 중요도 배분)")
    print("=" * 50)

    reset_save_dir()

    # 1단계: 목록 수집
    prec_list = collect_all()
    print(f"\n목록 수집 완료: 총 {len(prec_list)}건")

    # 분야별 현황 출력
    from collections import Counter
    domain_count = Counter(p.get("분야", "미분류") for p in prec_list)
    print("\n[분야별 수집 현황]")
    for domain, target, _ in DOMAIN_QUERIES:
        print(f"  {domain}: {domain_count.get(domain, 0)}건 / 목표 {target}건")

    # 목록 저장
    list_json = os.path.join(SAVE_DIR, "prec_list_1008.json")
    with open(list_json, "w", encoding="utf-8") as f:
        json.dump(prec_list, f, ensure_ascii=False, indent=2)
    print(f"\n목록 저장: {list_json}")

    # 2단계: 판결문 본문 수집
    print("\n" + "=" * 50)
    print("판결문 본문 수집 시작")
    fail_log = []
    for idx, prec in enumerate(prec_list, 1):
        prec_id = prec.get("판례일련번호", "")
        domain = prec.get("분야", "기타")
        case_name = prec.get("사건명", "사건명없음")[:50]
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", case_name)
        filename = f"{domain}_{prec_id}_{safe_name}.txt"

        print(f"[{idx}/{len(prec_list)}] [{domain}] {prec_id} - {case_name[:25]}...")

        if not prec_id:
            fail_log.append("UNKNOWN")
            continue

        text = fetch_detail_xml(prec_id)
        if text:
            save_text(filename, text)
            print(f"  ✔ 저장됨")
        else:
            print(f"  ✘ 본문 없음")
            fail_log.append(prec_id)

        time.sleep(TEXT_DELAY)

    # 최종 결과
    print("\n" + "=" * 50)
    print(f"모든 작업 완료. 저장 폴더: {SAVE_DIR}")
    print(f"성공: {len(prec_list) - len(fail_log)}건 | 실패: {len(fail_log)}건")
    if fail_log:
        print("실패 ID:", fail_log)

if __name__ == "__main__":
    main()
