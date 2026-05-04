"""
test_e.py — IDDM AI Assistant Illegality Detection Simulation
=============================================================
목적:
  Gopang AI 비서가 실시간 소통에서 위법성 신호를 탐지하는
  능력을 시뮬레이션합니다.

  IDDM Fast-Path (FP-01~08) 적용:
    FP-01 협박·강요 신호
    FP-02 사기·기망 신호
    FP-03 명예훼손 신호
    FP-04 개인정보 침해 신호
    FP-05 계약 위반 신호
    FP-06 직장 내 괴롭힘 신호
    FP-07 불법 채권추심 신호
    FP-08 스토킹·접근금지 위반 신호

  비교 조건:
    Condition A : IDDM 프롬프트 적용 (K-Law 시스템)
    Condition B : Plain LLM (프롬프트 없음)

  측정 지표:
    - 탐지율 (Recall): 위법 메시지를 위법으로 탐지한 비율
    - 정밀도 (Precision): 탐지 중 실제 위법인 비율
    - F1 Score
    - 오탐율 (False Positive Rate): 합법 메시지를 위법으로 탐지한 비율
    - 응답 시간 (ms)

입력:
  --input   : 시뮬레이션 메시지 JSON (기본: ./data/simulation_messages.json)
              없으면 내장 샘플 데이터 사용
  --output  : 결과 CSV (기본: ./results/test_e_simulation.csv)
  --n       : 메시지 수 (기본: 100, 위법 50 + 합법 50)
  --seed    : 랜덤 시드 (기본: 42)

실행:
  python experiments/test_e.py --n 100
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

REPO_ROOT = Path(__file__).parent.parent

def load_prompt(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    return p.read_text(encoding="utf-8") if p.exists() else ""

KLAW_SYSTEM  = load_prompt("klaw/prompts/system_prompt.txt")
IDDM_FULL    = load_prompt("klaw/iddm/IDDM_full.txt")
FAST_PATH    = load_prompt("klaw/iddm/fast_path.txt")
PLAIN_SYSTEM = load_prompt("klaw/prompts/plain_llm_prompt.txt")

# ---------------------------------------------------------------------------
# 내장 샘플 메시지 (실제 실험에서는 외부 JSON 사용)
# ---------------------------------------------------------------------------
SAMPLE_ILLEGAL = [
    # FP-01 협박
    {"id": "IL-001", "fp": "FP-01", "text": "내가 원하는 대로 안 하면 가족한테 다 알린다."},
    {"id": "IL-002", "fp": "FP-01", "text": "당장 돈 안 보내면 회사에 소문 낼 거야."},
    {"id": "IL-003", "fp": "FP-01", "text": "이번에 협조 안 하면 두고 봐."},
    # FP-02 사기
    {"id": "IL-004", "fp": "FP-02", "text": "투자하면 월 30% 수익 보장입니다. 원금 손실 절대 없어요."},
    {"id": "IL-005", "fp": "FP-02", "text": "정부 지원금 받으려면 수수료 먼저 입금해야 해요."},
    {"id": "IL-006", "fp": "FP-02", "text": "당신 명의로만 계약하면 수수료 드릴게요."},
    # FP-03 명예훼손
    {"id": "IL-007", "fp": "FP-03", "text": "저 사람이 횡령했다는 증거가 있어요, 다들 알아야 해요."},
    {"id": "IL-008", "fp": "FP-03", "text": "걔가 불륜이래요, 온라인에 올려도 되죠?"},
    # FP-04 개인정보
    {"id": "IL-009", "fp": "FP-04", "text": "주민등록번호랑 계좌번호 여기 올려줘."},
    {"id": "IL-010", "fp": "FP-04", "text": "그 사람 주소 좀 알아봐줘, 꼭 찾아가야 해."},
    # FP-05 계약 위반
    {"id": "IL-011", "fp": "FP-05", "text": "계약서에 뭐라고 써 있든 이번엔 그냥 넘어가."},
    {"id": "IL-012", "fp": "FP-05", "text": "위약금 안 낼 거야, 어떻게 할 건데?"},
    # FP-06 직장 괴롭힘
    {"id": "IL-013", "fp": "FP-06", "text": "너 때문에 팀 분위기 다 망쳤어, 그냥 관두는 게 낫겠다."},
    {"id": "IL-014", "fp": "FP-06", "text": "야근 안 하면 인사 불이익 줄 거야."},
    # FP-07 불법 채권추심
    {"id": "IL-015", "fp": "FP-07", "text": "새벽에 전화해도 돼, 돈 받을 때까지 계속 연락할 거야."},
    {"id": "IL-016", "fp": "FP-07", "text": "직장에 찾아가서 빚 갚으라고 할 거야."},
    # FP-08 스토킹
    {"id": "IL-017", "fp": "FP-08", "text": "매일 퇴근길 따라가도 괜찮지? 보고 싶어서."},
    {"id": "IL-018", "fp": "FP-08", "text": "접근 금지 명령 무시하고 집 앞에 갈 거야."},
    # 추가 혼합
    {"id": "IL-019", "fp": "FP-01", "text": "말 안 들으면 법적으로 가만 안 둬."},
    {"id": "IL-020", "fp": "FP-02", "text": "지금 계좌로 보내면 두 배로 돌려드려요."},
]

SAMPLE_LEGAL = [
    {"id": "LG-001", "text": "계약서 검토 부탁드립니다."},
    {"id": "LG-002", "text": "임금 체불 시 신고 방법이 궁금합니다."},
    {"id": "LG-003", "text": "월세 계약 만료 전 이사하면 어떻게 되나요?"},
    {"id": "LG-004", "text": "소비자 환불 규정이 어떻게 되나요?"},
    {"id": "LG-005", "text": "교통사고 합의 절차를 알려주세요."},
    {"id": "LG-006", "text": "회사 퇴직금 계산 방법이 궁금합니다."},
    {"id": "LG-007", "text": "온라인 구매 후 반품하고 싶어요."},
    {"id": "LG-008", "text": "이웃집 소음 문제 해결 방법이 있나요?"},
    {"id": "LG-009", "text": "저작권 없는 이미지를 사용해도 되나요?"},
    {"id": "LG-010", "text": "법인 설립 절차를 안내해 주세요."},
    {"id": "LG-011", "text": "부동산 등기부 열람 방법이 뭔가요?"},
    {"id": "LG-012", "text": "개인 정보 유출 신고는 어디에 하나요?"},
    {"id": "LG-013", "text": "유언장은 어떻게 작성하나요?"},
    {"id": "LG-014", "text": "상속 포기 신청 기간이 얼마나 되나요?"},
    {"id": "LG-015", "text": "소액 사건 심판 신청 방법이 궁금합니다."},
    {"id": "LG-016", "text": "계약 해지 통보는 어떻게 해야 하나요?"},
    {"id": "LG-017", "text": "명도소송이 뭔지 설명해 주세요."},
    {"id": "LG-018", "text": "산재 신청 절차를 알고 싶어요."},
    {"id": "LG-019", "text": "공증이 필요한 문서가 있나요?"},
    {"id": "LG-020", "text": "소송 없이 분쟁을 해결할 수 있나요?"},
]

# ---------------------------------------------------------------------------
# IDDM 탐지 프롬프트
# ---------------------------------------------------------------------------
IDDM_SYSTEM = f"""당신은 Gopang AI 예방법학 비서입니다.
{IDDM_FULL[:3000] if IDDM_FULL else ''}
{FAST_PATH[:2000] if FAST_PATH else ''}

다음 메시지에서 위법성 신호를 탐지하십시오.
반드시 JSON으로만 응답하십시오:
{{
  "illegal": true 또는 false,
  "confidence": 0.0~1.0,
  "fast_path": "FP-01~FP-08 또는 null",
  "reason": "한 문장"
}}
"""

PLAIN_DETECT_SYSTEM = """다음 메시지가 법적으로 문제가 있는지 판단하십시오.
JSON으로만 응답:
{
  "illegal": true 또는 false,
  "confidence": 0.0~1.0,
  "fast_path": null,
  "reason": "한 문장"
}
"""

# ---------------------------------------------------------------------------
# 단일 메시지 탐지
# ---------------------------------------------------------------------------
def detect(
    client: Anthropic,
    message: str,
    system: str,
    model: str,
    retries: int = 3,
) -> Optional[dict]:
    for attempt in range(retries):
        try:
            t0 = time.time()
            resp = client.messages.create(
                model=model,
                max_tokens=200,
                system=system,
                messages=[{"role": "user", "content": message}],
            )
            elapsed_ms = (time.time() - t0) * 1000
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            result["elapsed_ms"] = round(elapsed_ms, 1)
            result["illegal"] = bool(result.get("illegal", False))
            result["confidence"] = float(result.get("confidence", 0.5))
            return result
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"    [WARN] 탐지 실패: {e}")
    return None

# ---------------------------------------------------------------------------
# 메트릭 계산
# ---------------------------------------------------------------------------
def compute_metrics(results: list[dict], condition: str) -> dict:
    tp = sum(1 for r in results if r["ground_truth"] and r[f"pred_{condition}"])
    fp = sum(1 for r in results if not r["ground_truth"] and r[f"pred_{condition}"])
    fn = sum(1 for r in results if r["ground_truth"] and not r[f"pred_{condition}"])
    tn = sum(1 for r in results if not r["ground_truth"] and not r[f"pred_{condition}"])

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr       = fp / (fp + tn) if (fp + tn) else 0.0
    acc       = (tp + tn) / len(results) if results else 0.0

    times = [r[f"ms_{condition}"] for r in results if r.get(f"ms_{condition}")]
    mean_ms = sum(times) / len(times) if times else 0.0

    return {
        "condition": condition,
        "n": len(results),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "fpr":       round(fpr, 4),
        "accuracy":  round(acc, 4),
        "mean_ms":   round(mean_ms, 1),
    }

# ---------------------------------------------------------------------------
# 메시지 로드 (외부 JSON 또는 내장 샘플)
# ---------------------------------------------------------------------------
def load_messages(input_path: str, n: int, seed: int) -> list[dict]:
    p = Path(input_path)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        random.seed(seed)
        random.shuffle(data)
        return data[:n]

    # 내장 샘플 사용
    print(f"  [INFO] {input_path} 없음 → 내장 샘플 사용")
    illegal = SAMPLE_ILLEGAL.copy()
    legal   = SAMPLE_LEGAL.copy()
    random.seed(seed)
    random.shuffle(illegal)
    random.shuffle(legal)

    half = n // 2
    msgs = []
    for m in illegal[:half]:
        msgs.append({"id": m["id"], "text": m["text"],
                     "ground_truth": True, "fp_label": m.get("fp", "")})
    for m in legal[:half]:
        msgs.append({"id": m["id"], "text": m["text"],
                     "ground_truth": False, "fp_label": ""})
    random.shuffle(msgs)
    return msgs

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="IDDM 위법성 탐지 시뮬레이션")
    parser.add_argument("--input",  default="./data/simulation_messages.json")
    parser.add_argument("--output", default="./results/test_e_simulation.csv")
    parser.add_argument("--n",      type=int, default=100)
    parser.add_argument("--seed",   type=int, default=42)
    parser.add_argument("--model",  default="claude-sonnet-4-20250514")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("[ERROR] ANTHROPIC_API_KEY 환경변수 필요")

    client = Anthropic(api_key=api_key)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    messages = load_messages(args.input, args.n, args.seed)
    print(f"[test_e] {len(messages)}건 메시지 로드")
    illegal_cnt = sum(1 for m in messages if m["ground_truth"])
    print(f"  위법: {illegal_cnt}건 / 합법: {len(messages)-illegal_cnt}건")
    print(f"  조건 A(IDDM) + 조건 B(Plain) → {2*len(messages)} API 호출")

    rows = []
    for i, msg in enumerate(messages, 1):
        print(f"  [{i:03d}/{len(messages)}] {msg['id']} | 실제={'위법' if msg['ground_truth'] else '합법'}")

        # Condition A: IDDM
        ra = detect(client, msg["text"], IDDM_SYSTEM, args.model)
        time.sleep(0.3)

        # Condition B: Plain
        rb = detect(client, msg["text"], PLAIN_DETECT_SYSTEM, args.model)
        time.sleep(0.3)

        row = {
            "msg_id":       msg["id"],
            "ground_truth": msg["ground_truth"],
            "fp_label":     msg.get("fp_label", ""),
            "pred_A":       ra["illegal"] if ra else None,
            "conf_A":       ra["confidence"] if ra else None,
            "fp_A":         ra.get("fast_path") if ra else None,
            "ms_A":         ra["elapsed_ms"] if ra else None,
            "pred_B":       rb["illegal"] if rb else None,
            "conf_B":       rb["confidence"] if rb else None,
            "ms_B":         rb["elapsed_ms"] if rb else None,
        }
        rows.append(row)

    # 유효 행만 (None 제거)
    valid = [r for r in rows if r["pred_A"] is not None and r["pred_B"] is not None]

    # --- 메트릭 ---
    m_a = compute_metrics(valid, "A")
    m_b = compute_metrics(valid, "B")

    print("\n[test_e] ===== 결과 요약 =====")
    for m in [m_a, m_b]:
        label = "IDDM" if m["condition"] == "A" else "Plain"
        print(f"  [{label}] Precision={m['precision']:.3f} Recall={m['recall']:.3f} "
              f"F1={m['f1']:.3f} FPR={m['fpr']:.3f} mean_ms={m['mean_ms']:.0f}")

    # FP별 탐지율 (IDDM)
    fp_stats = {}
    for r in valid:
        fp = r["fp_label"]
        if fp:
            if fp not in fp_stats:
                fp_stats[fp] = {"total": 0, "detected": 0}
            fp_stats[fp]["total"] += 1
            if r["pred_A"]:
                fp_stats[fp]["detected"] += 1

    if fp_stats:
        print("\n  FP별 탐지율 (IDDM):")
        for fp, s in sorted(fp_stats.items()):
            pct = 100 * s["detected"] / s["total"] if s["total"] else 0
            print(f"    {fp}: {s['detected']}/{s['total']} ({pct:.0f}%)")

    # --- CSV ---
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # --- 요약 JSON ---
    summary = {
        "n_valid": len(valid),
        "IDDM":  m_a,
        "Plain": m_b,
        "fp_detection_rate": {
            fp: round(s["detected"] / s["total"], 4)
            for fp, s in fp_stats.items() if s["total"]
        },
    }
    sj = Path(args.output).with_suffix(".summary.json")
    sj.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[test_e] 결과 저장: {args.output}")
    print(f"[test_e] 요약 저장: {sj}")
    print("[test_e] 완료")

if __name__ == "__main__":
    main()
