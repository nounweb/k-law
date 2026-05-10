"""
고팡(Gopang) 데모 서버 v3.0
FastAPI + WebSocket + SQLite + DeepSeek API + OpenHash 시뮬레이션

변경 사항 (v3):
  - anchor_telegram() → anchor_openhash() 교체
  - OpenHash 시뮬레이션 네트워크 (L1×10 + L2×4 + L3×3 + L4×2 + L5×1 = 20노드)
  - PLSM (확률적 계층 선택) 구현
  - Merkle Tree 루트 계산
  - PDV Records 테이블 신설 (Phase 6 스펙 KL-M-02)
  - PDV 서랍 분류 6개 카테고리
  - GET /openhash/status, GET /openhash/verify/{conv_id} 신규 엔드포인트
  - POST /pdv/analyze/{conv_id} 응답에 pdv + openhash 필드 추가
"""

import os, json, hashlib, time, asyncio, sqlite3, uuid, random, math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx
import jwt  # pip install PyJWT

# ──────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "")      # 더 이상 사용 안 함, 유지만
ANCHOR_CHANNEL_ID = os.getenv("ANCHOR_CHANNEL_ID", "")  # 더 이상 사용 안 함, 유지만
JWT_SECRET        = os.getenv("JWT_SECRET", "gopang-demo-secret-change-in-prod")
DB_PATH           = os.getenv("DB_PATH", "/opt/gopang/gopang_demo.db")

app = FastAPI(title="Gopang Demo Server", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer()


# ══════════════════════════════════════════════════
# ① OpenHash 시뮬레이션 네트워크 (인메모리)
#    L1×10 + L2×4 + L3×3 + L4×2 + L5×1 = 20 노드
#    gopang.net 단일 서버에서 Python dict로 에뮬레이션
# ══════════════════════════════════════════════════

# 노드 정의: (node_id, tier, name, region)
OPENHASH_NODE_DEFS = [
    # L1 — 읍면동 (10개)
    ("L1-001", "L1", "제주시_이도1동",   "jeju"),
    ("L1-002", "L1", "제주시_이도2동",   "jeju"),
    ("L1-003", "L1", "제주시_삼도동",    "jeju"),
    ("L1-004", "L1", "제주시_화북동",    "jeju"),
    ("L1-005", "L1", "제주시_아라동",    "jeju"),
    ("L1-006", "L1", "서귀포시_동홍동",  "seogwipo"),
    ("L1-007", "L1", "서귀포시_서홍동",  "seogwipo"),
    ("L1-008", "L1", "서귀포시_대정읍",  "seogwipo"),
    ("L1-009", "L1", "서귀포시_안덕면",  "seogwipo"),
    ("L1-010", "L1", "제주시_한림읍",    "jeju"),
    # L2 — 시군구 (4개)
    ("L2-001", "L2", "제주시",           "jeju"),
    ("L2-002", "L2", "서귀포시",         "seogwipo"),
    ("L2-003", "L2", "제주동부",         "jeju"),
    ("L2-004", "L2", "제주서부",         "jeju"),
    # L3 — 광역 (3개)
    ("L3-001", "L3", "제주특별자치도",    "jeju_province"),
    ("L3-002", "L3", "한국_남부권역",     "south_korea"),
    ("L3-003", "L3", "한국_중앙권역",     "central_korea"),
    # L4 — 국가 (2개)
    ("L4-001", "L4", "OpenHash_Korea",   "korea"),
    ("L4-002", "L4", "OpenHash_Asia",    "asia"),
    # L5 — 글로벌 (1개)
    ("L5-001", "L5", "OpenHash_Global",  "global"),
]

# 인메모리 노드 저장소: node_id → { node_id, tier, name, entries: [...], merkle_root }
_oh_nodes: dict[str, dict] = {}

def _init_openhash_nodes():
    """서버 시작 시 20개 노드 인메모리 초기화"""
    for (nid, tier, name, region) in OPENHASH_NODE_DEFS:
        _oh_nodes[nid] = {
            "node_id":     nid,
            "tier":        tier,
            "name":        name,
            "region":      region,
            "entries":     [],       # [{ hash, conv_id, timestamp, grade }]
            "merkle_root": "0" * 64,
            "updated_at":  datetime.utcnow().isoformat(),
        }

_init_openhash_nodes()

# 계층별 노드 목록 (편의 조회용)
def _nodes_by_tier(tier: str) -> list[dict]:
    return [n for n in _oh_nodes.values() if n["tier"] == tier]

# 상위 계층 매핑 (전파 경로)
_TIER_UP = {"L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5"}

def _merkle_root(hashes: list[str]) -> str:
    """간소 Merkle 루트: SHA-256 반복 결합"""
    if not hashes:
        return "0" * 64
    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])   # 홀수이면 마지막 복제
        layer = [
            hashlib.sha256((layer[i] + layer[i+1]).encode()).hexdigest()
            for i in range(0, len(layer), 2)
        ]
    return layer[0]

def _update_node_merkle(node_id: str):
    """노드 엔트리 전체로 Merkle 루트 재계산"""
    node = _oh_nodes[node_id]
    hashes = [e["hash"] for e in node["entries"]]
    node["merkle_root"] = _merkle_root(hashes)
    node["updated_at"]  = datetime.utcnow().isoformat()


# ── PLSM (Probabilistic Layer Selection Model) ──────────────────────────────
# grade별 계층 선택 확률 (스펙 §5.2 참조)
#   S0: L1 50%, L2 30%, L3 15%, L4 4%, L5 1%
#   S1: L1 30%, L2 35%, L3 25%, L4 8%,  L5 2%
#   S2: L1 15%, L2 25%, L3 35%, L4 20%, L5 5%
#   S3: L1 5%,  L2 10%, L3 30%, L4 40%, L5 15%

_PLSM_TABLE = {
    "S0": [("L1", 0.50), ("L2", 0.30), ("L3", 0.15), ("L4", 0.04), ("L5", 0.01)],
    "S1": [("L1", 0.30), ("L2", 0.35), ("L3", 0.25), ("L4", 0.08), ("L5", 0.02)],
    "S2": [("L1", 0.15), ("L2", 0.25), ("L3", 0.35), ("L4", 0.20), ("L5", 0.05)],
    "S3": [("L1", 0.05), ("L2", 0.10), ("L3", 0.30), ("L4", 0.40), ("L5", 0.15)],
}

def plsm_select_tier(grade: str) -> str:
    """PLSM: grade → 등록 계층 확률적 선택"""
    table = _PLSM_TABLE.get(grade, _PLSM_TABLE["S0"])
    r = random.random()
    cumulative = 0.0
    for tier, prob in table:
        cumulative += prob
        if r < cumulative:
            return tier
    return table[-1][0]

def _select_node_in_tier(tier: str) -> dict:
    """해당 계층에서 엔트리 수가 가장 적은 노드 선택 (부하 균형)"""
    candidates = _nodes_by_tier(tier)
    return min(candidates, key=lambda n: len(n["entries"]))

def _propagate_up(entry_hash: str, from_tier: str, conv_id: str, grade: str,
                  timestamp: str) -> list[str]:
    """상위 계층으로 해시 전파, 경유한 node_id 목록 반환"""
    propagated = []
    current_tier = from_tier
    while current_tier in _TIER_UP:
        upper_tier = _TIER_UP[current_tier]
        upper_node = _select_node_in_tier(upper_tier)
        # 체인 해시: 이전 Merkle 루트 + 새 해시
        chain_hash = hashlib.sha256(
            (upper_node["merkle_root"] + entry_hash).encode()
        ).hexdigest()
        upper_node["entries"].append({
            "hash":      chain_hash,
            "conv_id":   conv_id,
            "grade":     grade,
            "timestamp": timestamp,
            "propagated_from": current_tier,
        })
        _update_node_merkle(upper_node["node_id"])
        propagated.append(upper_node["node_id"])
        current_tier = upper_tier
    return propagated


async def anchor_openhash(conv_id: str, content_hash: str, grade: str,
                          timestamp: str) -> dict:
    """
    OpenHash 시뮬레이션 등록 (인메모리).
    반환: { anchor_id, tier, node_id, node_name, chain_hash,
             merkle_root, propagated_to, timestamp }
    """
    # 1. PLSM으로 기록 계층 결정
    selected_tier = plsm_select_tier(grade)

    # 2. 해당 계층 노드 선택
    target_node = _select_node_in_tier(selected_tier)

    # 3. 체인 해시 = SHA-256(이전 Merkle 루트 + content_hash)
    chain_hash = hashlib.sha256(
        (target_node["merkle_root"] + content_hash).encode()
    ).hexdigest()

    # 4. 노드에 엔트리 등록
    target_node["entries"].append({
        "hash":      chain_hash,
        "conv_id":   conv_id,
        "grade":     grade,
        "timestamp": timestamp,
    })
    _update_node_merkle(target_node["node_id"])

    entry_index = len(target_node["entries"])  # 1-based

    # 5. 앵커 ID 생성: OH-{tier}-{node_id}-{entry_index}-{chain_hash[:8]}
    anchor_id = (
        f"OH-{selected_tier}-{target_node['node_id']}-"
        f"{entry_index}-{chain_hash[:8]}"
    )

    # 6. 상위 계층으로 전파
    propagated_to = _propagate_up(
        chain_hash, selected_tier, conv_id, grade, timestamp
    )

    return {
        "anchor_id":    anchor_id,
        "tier":         selected_tier,
        "node_id":      target_node["node_id"],
        "node_name":    target_node["name"],
        "chain_hash":   chain_hash,
        "merkle_root":  target_node["merkle_root"],
        "propagated_to": propagated_to,
        "timestamp":    timestamp,
    }


# ══════════════════════════════════════════════════
# ② DB 초기화 (신규 테이블 포함)
# ══════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id   TEXT PRIMARY KEY,
        username  TEXT UNIQUE NOT NULL,
        password  TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS conversations (
        conv_id    TEXT PRIMARY KEY,
        user_a     TEXT NOT NULL,
        user_b     TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS messages (
        msg_id        TEXT PRIMARY KEY,
        conv_id       TEXT NOT NULL,
        sender_id     TEXT NOT NULL,
        content       TEXT NOT NULL,
        phase_grade   TEXT DEFAULT 'S0',
        phase_json    TEXT DEFAULT '{}',
        fast_keywords TEXT DEFAULT '[]',
        hash_sha256   TEXT,
        anchor_l0     TEXT,
        analyzed      INTEGER DEFAULT 0,
        timestamp     TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS pdv_log (
        pdv_id      TEXT PRIMARY KEY,
        conv_id     TEXT,
        msg_id      TEXT,
        user_id     TEXT,
        grade       TEXT,
        score       REAL DEFAULT 0.0,
        summary     TEXT DEFAULT '',
        hash_sha256 TEXT,
        anchor_l0   TEXT,
        timestamp   TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS conv_analysis (
        analysis_id   TEXT PRIMARY KEY,
        conv_id       TEXT NOT NULL,
        overall_grade TEXT,
        overall_score REAL DEFAULT 0.0,
        summary       TEXT DEFAULT '',
        legal_findings TEXT DEFAULT '[]',
        recommendation TEXT DEFAULT '',
        raw_json      TEXT DEFAULT '{}',
        anchor_l0     TEXT,
        created_at    TEXT DEFAULT (datetime('now'))
    );

    -- ★ 신규: PDV Records (Phase 6 KL-M-02 스펙)
    CREATE TABLE IF NOT EXISTS pdv_records (
        pdv_record_id  TEXT PRIMARY KEY,
        conv_id        TEXT NOT NULL,
        user_id        TEXT NOT NULL,
        grade          TEXT NOT NULL,
        drawer         TEXT NOT NULL DEFAULT 'GENERAL',
        content_hash   TEXT NOT NULL,
        content_enc    TEXT,
        analysis_json  TEXT,
        fast_path_json TEXT,
        legal_refs     TEXT DEFAULT '[]',
        anchor_id      TEXT,
        anchor_tier    TEXT,
        anchor_node    TEXT,
        anchor_chain   TEXT,
        propagated_to  TEXT DEFAULT '[]',
        retention_days INTEGER DEFAULT 90,
        created_at     TEXT DEFAULT (datetime('now')),
        expires_at     TEXT
    );

    -- ★ 신규: OpenHash 영구 앵커 로그 (인메모리 보완용)
    CREATE TABLE IF NOT EXISTS openhash_anchors (
        anchor_id      TEXT PRIMARY KEY,
        conv_id        TEXT NOT NULL,
        tier           TEXT NOT NULL,
        node_id        TEXT NOT NULL,
        node_name      TEXT NOT NULL,
        content_hash   TEXT NOT NULL,
        chain_hash     TEXT NOT NULL,
        merkle_root    TEXT NOT NULL,
        grade          TEXT NOT NULL,
        propagated_to  TEXT DEFAULT '[]',
        created_at     TEXT DEFAULT (datetime('now'))
    );
    """)

    # 기존 DB 마이그레이션 (컬럼 추가 시 오류 무시)
    for sql in [
        "ALTER TABLE messages ADD COLUMN fast_keywords TEXT DEFAULT '[]'",
        "ALTER TABLE messages ADD COLUMN analyzed INTEGER DEFAULT 0",
        "ALTER TABLE pdv_log ADD COLUMN conv_id TEXT",
        "ALTER TABLE pdv_log ADD COLUMN score REAL DEFAULT 0.0",
        "ALTER TABLE pdv_log ADD COLUMN summary TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass

    conn.commit()
    conn.close()

init_db()


# ══════════════════════════════════════════════════
# ③ PDV 서랍 분류 (6개 카테고리)
# ══════════════════════════════════════════════════

_DRAWER_KEYWORDS = {
    "FINANCIAL":  ["계좌","이체","송금","대출","보험","투자","주식","세금",
                   "환급","배당","펀드","증권","카드","금리","입금","공탁"],
    "MEDICAL":    ["진단","처방","병원","의사","치료","약","수술","증상",
                   "입원","의료","검사","건강","환자","약국"],
    "EDUCATION":  ["학교","성적","입학","자격증","교육","학위","수강",
                   "시험","장학금","졸업","수업","강의","학원"],
    "ADMIN":      ["민원","계약","공문","서류","신청","허가","행정",
                   "등록","신고","허가증","위임","공증","관청"],
    "TRANSPORT":  ["차량","교통","운전","사고","면허","주차","버스",
                   "택시","렌트","항공","선박","철도"],
}

def pdv_classify_drawer(text: str) -> str:
    """대화 전문을 분석해 6개 PDV 서랍 중 하나 반환"""
    scores = {drawer: 0 for drawer in _DRAWER_KEYWORDS}
    for drawer, kws in _DRAWER_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                scores[drawer] += 1
    best_drawer = max(scores, key=scores.get)
    return best_drawer if scores[best_drawer] > 0 else "GENERAL"


# ══════════════════════════════════════════════════
# ④ 유틸리티
# ══════════════════════════════════════════════════

def make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()

def make_jwt(user_id: str, username: str) -> str:
    payload = {
        "sub":      user_id,
        "username": username,
        "exp":      datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="인증 토큰이 유효하지 않습니다")

def current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return verify_jwt(creds.credentials)


# ══════════════════════════════════════════════════
# ⑤ Fast-Path 로컬 키워드 스캔 (API 비용 없음)
# ══════════════════════════════════════════════════

FAST_PATH_KEYWORDS = [
    "검사", "검찰", "경찰", "수사관", "형사", "법원", "판사", "수사",
    "입금", "이체", "송금", "계좌", "안전계좌", "공탁금", "보증금",
    "범죄", "연루", "체포", "구속", "영장", "기소", "피의자",
    "금융감독원", "금융위원회", "국세청", "국정원", "인터폴",
    "주민번호", "주민등록", "비밀번호", "카드번호", "계좌번호",
    "즉시 이체", "지금 바로", "오늘 안에", "오늘까지", "내일까지",
    "피해예방", "명의도용", "자금세탁", "가상계좌",
]

S3_COMBO_GROUPS = [
    {"검사", "계좌"},   {"검사", "입금"},  {"경찰", "이체"},
    {"경찰", "계좌"},   {"수사", "계좌"},  {"검찰", "송금"},
    {"법원", "이체"},   {"수사관", "입금"},{"안전계좌", "입금"},
    {"구속", "이체"},   {"금융감독원", "계좌"},
]

def fast_path_scan(content: str) -> dict:
    found = [kw for kw in FAST_PATH_KEYWORDS if kw in content]
    if not found:
        return {"grade": "S0", "keywords": [], "warning": False, "reason": "정상"}

    found_set = set(found)
    for combo in S3_COMBO_GROUPS:
        if combo.issubset(found_set):
            return {
                "grade":    "S3",
                "keywords": found,
                "warning":  True,
                "reason":   f"보이스피싱 패턴 감지: {', '.join(combo)}"
            }

    count = len(found)
    if count >= 4:
        grade, reason = "S3", f"다수 위험 키워드 동시 탐지 ({count}개)"
    elif count >= 2:
        grade, reason = "S2", f"복수 주의 키워드 탐지: {', '.join(found)}"
    else:
        grade, reason = "S1", f"주의 키워드 탐지: {', '.join(found)}"

    return {"grade": grade, "keywords": found, "warning": True, "reason": reason}


# ══════════════════════════════════════════════════
# ⑥ 배치 분석 — DeepSeek API (대화 종료 시 1회)
# ══════════════════════════════════════════════════

BATCH_SYSTEM_PROMPT = """당신은 고팡(Gopang)의 AI 법학 비서입니다.
아래 대화 전체를 Phase 0~5 파이프라인으로 분석하고,
반드시 JSON 형식으로만 응답하십시오. 마크다운 코드블록 없이 순수 JSON만.

분석 기준:
- 보이스피싱, 사기, 협박, 불법 금융 거래 탐지
- 형사/민사/소비자보호법 관련 위법 여부
- 각 메시지별 위험도 + 전체 대화 종합 등급

등급 기준:
- S0: 정상 (score < 0.2)
- S1: 주의 (0.2 ≤ score < 0.4)
- S2: 경고 (0.4 ≤ score < 0.7)
- S3: 차단/신고 권고 (score ≥ 0.7)

응답 JSON 형식 (다른 텍스트 일절 없이 이 JSON만):
{
  "overall_grade": "S0",
  "overall_score": 0.0,
  "summary": "대화 전체 요약",
  "messages": [
    {
      "msg_id": "메시지ID",
      "grade": "S0",
      "score": 0.0,
      "reason": "판단 근거"
    }
  ],
  "legal_findings": ["관련 법령 또는 판단 근거"],
  "recommendation": "사용자에게 전달할 권고 사항"
}"""

async def run_batch_analysis(messages: list[dict]) -> dict:
    """대화 전체 일괄 분석 — 대화 종료 시 1회만 호출"""
    if not DEEPSEEK_API_KEY:
        grades = [m.get("fast_grade", "S0") for m in messages]
        worst = "S0"
        for g in ["S3", "S2", "S1", "S0"]:
            if g in grades:
                worst = g
                break
        return {
            "overall_grade": worst,
            "overall_score": {"S0": 0.0, "S1": 0.3, "S2": 0.55, "S3": 0.85}[worst],
            "summary": "API 키 미설정 — Fast-Path 키워드 스캔 결과 기반 데모 분석",
            "messages": [
                {
                    "msg_id": m["msg_id"],
                    "grade":  m.get("fast_grade", "S0"),
                    "score":  {"S0": 0.0, "S1": 0.3, "S2": 0.55, "S3": 0.85}.get(m.get("fast_grade", "S0"), 0.0),
                    "reason": f"Fast-Path 탐지 키워드: {', '.join(m.get('keywords', [])) or '없음'}"
                }
                for m in messages
            ],
            "legal_findings": [],
            "recommendation": "DeepSeek API 키를 설정하면 정밀 법학 분석이 활성화됩니다."
        }

    conv_text = "\n".join([
        f"[{m['sender']} | msg_id:{m['msg_id'][:8]}] {m['content']}"
        for m in messages
    ])

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user",   "content": f"분석할 대화 내용:\n{conv_text}\n\n메시지 ID 목록: {[m['msg_id'] for m in messages]}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens":  2000
                }
            )
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {
            "overall_grade": "S0",
            "overall_score": 0.0,
            "summary":       f"배치 분석 오류: {str(e)}",
            "messages":      [{"msg_id": m["msg_id"], "grade": "S0", "score": 0.0, "reason": "분석 실패"} for m in messages],
            "legal_findings":  [],
            "recommendation":  "분석 중 오류가 발생했습니다. 로그를 확인하세요."
        }


# ══════════════════════════════════════════════════
# ⑦ WebSocket 연결 관리
# ══════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, conv_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(conv_id, []).append(ws)

    def disconnect(self, conv_id: str, ws: WebSocket):
        if conv_id in self.active:
            self.active[conv_id] = [w for w in self.active[conv_id] if w != ws]

    async def broadcast(self, conv_id: str, message: dict):
        for ws in self.active.get(conv_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


# ══════════════════════════════════════════════════
# ⑧ REST API — 인증
# ══════════════════════════════════════════════════

class RegisterReq(BaseModel):
    username: str
    password: str

class LoginReq(BaseModel):
    username: str
    password: str

class ConvReq(BaseModel):
    target_username: str

@app.post("/auth/register")
async def register(req: RegisterReq):
    conn = get_db()
    user_id = str(uuid.uuid4())
    pw_hash = make_hash(req.password)
    try:
        conn.execute(
            "INSERT INTO users (user_id, username, password) VALUES (?,?,?)",
            (user_id, req.username, pw_hash)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")
    finally:
        conn.close()
    token = make_jwt(user_id, req.username)
    return {"token": token, "user_id": user_id, "username": req.username}

@app.post("/auth/login")
async def login(req: LoginReq):
    conn = get_db()
    pw_hash = make_hash(req.password)
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (req.username, pw_hash)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="사용자명 또는 비밀번호가 잘못되었습니다")
    token = make_jwt(row["user_id"], row["username"])
    return {"token": token, "user_id": row["user_id"], "username": row["username"]}

@app.get("/users")
async def list_users(user=Depends(current_user)):
    conn = get_db()
    rows = conn.execute("SELECT user_id, username, created_at FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════
# ⑨ REST API — 대화방
# ══════════════════════════════════════════════════

@app.post("/conversations")
async def create_conversation(req: ConvReq, user=Depends(current_user)):
    conn = get_db()
    target = conn.execute("SELECT * FROM users WHERE username=?", (req.target_username,)).fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="대상 사용자를 찾을 수 없습니다")
    existing = conn.execute(
        "SELECT conv_id FROM conversations WHERE (user_a=? AND user_b=?) OR (user_a=? AND user_b=?)",
        (user["sub"], target["user_id"], target["user_id"], user["sub"])
    ).fetchone()
    if existing:
        conn.close()
        return {"conv_id": existing["conv_id"], "status": "existing"}
    conv_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO conversations (conv_id, user_a, user_b) VALUES (?,?,?)",
        (conv_id, user["sub"], target["user_id"])
    )
    conn.commit()
    conn.close()
    return {"conv_id": conv_id, "status": "created"}

@app.get("/conversations")
async def get_conversations(user=Depends(current_user)):
    conn = get_db()
    rows = conn.execute(
        """SELECT c.conv_id, c.created_at,
                  ua.username as user_a_name, ub.username as user_b_name
           FROM conversations c
           JOIN users ua ON c.user_a = ua.user_id
           JOIN users ub ON c.user_b = ub.user_id
           WHERE c.user_a=? OR c.user_b=?""",
        (user["sub"], user["sub"])
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        other = r["user_b_name"] if r["user_a_name"] == user["username"] else r["user_a_name"]
        result.append({"conv_id": r["conv_id"], "with": other, "created_at": r["created_at"]})
    return result

@app.get("/messages/{conv_id}")
async def get_messages(conv_id: str, user=Depends(current_user)):
    conn = get_db()
    rows = conn.execute(
        """SELECT m.*, u.username as sender_name
           FROM messages m JOIN users u ON m.sender_id = u.user_id
           WHERE m.conv_id=? ORDER BY m.timestamp ASC LIMIT 200""",
        (conv_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/pdv")
async def get_pdv(user=Depends(current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pdv_log WHERE user_id=? ORDER BY timestamp DESC LIMIT 50",
        (user["sub"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════
# ⑩ 배치 분석 엔드포인트 (대화 종료 시 호출)
#    POST /pdv/analyze/{conv_id}
#    Step 1: K-Law 분석 → Step 2: PDV 저장 → Step 3: OpenHash 등록
# ══════════════════════════════════════════════════

@app.post("/pdv/analyze/{conv_id}")
async def analyze_conversation(conv_id: str, user=Depends(current_user)):
    """
    대화방 퇴장 시점에 호출.
    1) K-Law 배치 분석 (DeepSeek)
    2) PDV Records 저장 (Phase 6 스펙)
    3) OpenHash 시뮬레이션 등록 (anchor_telegram 교체)
    """
    conn = get_db()

    # 대화 참여자 확인
    conv = conn.execute(
        "SELECT * FROM conversations WHERE conv_id=? AND (user_a=? OR user_b=?)",
        (conv_id, user["sub"], user["sub"])
    ).fetchone()
    if not conv:
        conn.close()
        raise HTTPException(status_code=403, detail="이 대화방에 접근할 수 없습니다")

    # 메시지 로드
    rows = conn.execute(
        """SELECT m.msg_id, m.content, m.fast_keywords, m.phase_grade,
                  u.username as sender
           FROM messages m
           JOIN users u ON m.sender_id = u.user_id
           WHERE m.conv_id=?
           ORDER BY m.timestamp ASC""",
        (conv_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_messages", "message": "분석할 메시지가 없습니다"}

    messages = [
        {
            "msg_id":     r["msg_id"],
            "content":    r["content"],
            "sender":     r["sender"],
            "fast_grade": r["phase_grade"] or "S0",
            "keywords":   json.loads(r["fast_keywords"] or "[]")
        }
        for r in rows
    ]

    # ── Step 1: K-Law 배치 분석 ────────────────────────────────────────
    result = await run_batch_analysis(messages)

    overall_grade = result.get("overall_grade", "S0")
    overall_score = result.get("overall_score", 0.0)
    now_iso       = datetime.utcnow().isoformat()

    # 대화 전문 합산 (서랍 분류 + 해시용)
    full_text = " ".join(m["content"] for m in messages)

    # content_hash = SHA-256(대화원문 + 분석결과 + conv_id + timestamp)
    content_hash = make_hash(
        full_text + json.dumps(result, ensure_ascii=False) + conv_id + now_iso
    )

    # ── Step 2: PDV Records 저장 ────────────────────────────────────────
    drawer         = pdv_classify_drawer(full_text)
    is_s0          = (overall_grade == "S0")
    retention_days = 90 if is_s0 else 1825   # S0=90일, S1~S3=5년
    expires_at     = (
        datetime.utcnow() + timedelta(days=retention_days)
    ).isoformat()

    # S0: 간소 기록 (원문 미저장), S1~S3: 전체 기록
    content_enc    = None if is_s0 else full_text   # 실제 배포 시 AES-256 암호화
    analysis_json  = json.dumps(result, ensure_ascii=False)
    fast_path_json = json.dumps(
        [{"msg_id": m["msg_id"], "grade": m["fast_grade"],
          "keywords": m["keywords"]} for m in messages],
        ensure_ascii=False
    )
    legal_refs     = json.dumps(result.get("legal_findings", []), ensure_ascii=False)

    # ── Step 3: OpenHash 시뮬레이션 등록 ───────────────────────────────
    oh_result = await anchor_openhash(
        conv_id      = conv_id,
        content_hash = content_hash,
        grade        = overall_grade,
        timestamp    = now_iso,
    )
    anchor_id = oh_result["anchor_id"]

    # DB 저장 (한 트랜잭션)
    conn = get_db()
    analysis_id   = str(uuid.uuid4())
    pdv_record_id = str(uuid.uuid4())

    # conv_analysis 테이블 (기존 호환 유지)
    conn.execute(
        """INSERT INTO conv_analysis
           (analysis_id, conv_id, overall_grade, overall_score, summary,
            legal_findings, recommendation, raw_json, anchor_l0)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            analysis_id, conv_id, overall_grade, overall_score,
            result.get("summary", ""),
            legal_refs,
            result.get("recommendation", ""),
            analysis_json,
            anchor_id,   # ← anchor_telegram → anchor_openhash로 교체
        )
    )

    # pdv_records 테이블 (신규, Phase 6 스펙)
    conn.execute(
        """INSERT INTO pdv_records
           (pdv_record_id, conv_id, user_id, grade, drawer,
            content_hash, content_enc, analysis_json, fast_path_json,
            legal_refs, anchor_id, anchor_tier, anchor_node, anchor_chain,
            propagated_to, retention_days, created_at, expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pdv_record_id, conv_id, user["sub"], overall_grade, drawer,
            content_hash, content_enc, analysis_json, fast_path_json,
            legal_refs,
            anchor_id,
            oh_result["tier"],
            oh_result["node_id"],
            oh_result["chain_hash"],
            json.dumps(oh_result["propagated_to"], ensure_ascii=False),
            retention_days,
            now_iso,
            expires_at,
        )
    )

    # openhash_anchors 테이블 (영구 로그)
    conn.execute(
        """INSERT INTO openhash_anchors
           (anchor_id, conv_id, tier, node_id, node_name,
            content_hash, chain_hash, merkle_root, grade,
            propagated_to, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            anchor_id, conv_id,
            oh_result["tier"], oh_result["node_id"], oh_result["node_name"],
            content_hash, oh_result["chain_hash"], oh_result["merkle_root"],
            overall_grade,
            json.dumps(oh_result["propagated_to"], ensure_ascii=False),
            now_iso,
        )
    )

    # 메시지별 PDV 로그 업데이트 (기존 호환)
    msg_results = {m["msg_id"]: m for m in result.get("messages", [])}
    for msg in messages:
        mid   = msg["msg_id"]
        msg_r = msg_results.get(mid, {})
        grade = msg_r.get("grade", msg["fast_grade"])
        score = msg_r.get("score", 0.0)
        reason= msg_r.get("reason", "")
        msg_hash = make_hash(msg["content"] + mid)

        conn.execute(
            "UPDATE messages SET phase_grade=?, phase_json=?, hash_sha256=?, anchor_l0=?, analyzed=1 WHERE msg_id=?",
            (grade, json.dumps(msg_r, ensure_ascii=False), msg_hash, anchor_id, mid)
        )
        pdv_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO pdv_log
               (pdv_id, conv_id, msg_id, user_id, grade, score, summary, hash_sha256, anchor_l0)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pdv_id, conv_id, mid, user["sub"], grade, score, reason, msg_hash, anchor_id)
        )

    conn.commit()
    conn.close()

    # ── 응답 반환 ────────────────────────────────────────────────────────
    return {
        "status":         "ok",
        "analysis_id":    analysis_id,
        "conv_id":        conv_id,
        "overall_grade":  overall_grade,
        "overall_score":  overall_score,
        "summary":        result.get("summary", ""),
        "legal_findings": result.get("legal_findings", []),
        "recommendation": result.get("recommendation", ""),
        "messages":       result.get("messages", []),
        "hash":           content_hash,
        "anchor_l0":      anchor_id,   # 기존 필드 호환 유지
        "analyzed_count": len(messages),

        # ★ 신규 PDV 필드
        "pdv": {
            "pdv_record_id": pdv_record_id,
            "drawer":        drawer,
            "retention_days":retention_days,
            "grade":         overall_grade,
            "expires_at":    expires_at,
            "content_hash":  content_hash,
        },

        # ★ 신규 OpenHash 필드
        "openhash": {
            "anchor_id":    anchor_id,
            "tier":         oh_result["tier"],
            "node_id":      oh_result["node_id"],
            "node_name":    oh_result["node_name"],
            "chain_hash":   oh_result["chain_hash"],
            "merkle_root":  oh_result["merkle_root"],
            "propagated_to":oh_result["propagated_to"],
            "timestamp":    now_iso,
        }
    }


@app.get("/pdv/analysis/{conv_id}")
async def get_conv_analysis(conv_id: str, user=Depends(current_user)):
    """특정 대화방의 최신 배치 분석 결과 조회"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM conv_analysis WHERE conv_id=? ORDER BY created_at DESC LIMIT 1",
        (conv_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"status": "not_analyzed"}
    return dict(row)


# ══════════════════════════════════════════════════
# ⑪ OpenHash 신규 엔드포인트
# ══════════════════════════════════════════════════

@app.get("/openhash/status")
async def openhash_status(user=Depends(current_user)):
    """
    20개 노드의 현재 인메모리 상태 반환.
    디버그 패널 OpenHash 탭에서 표시.
    """
    nodes = []
    total_entries = 0
    last_anchor   = None

    # DB에서 최신 앵커 조회
    conn = get_db()
    last_row = conn.execute(
        "SELECT anchor_id FROM openhash_anchors ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if last_row:
        last_anchor = last_row["anchor_id"]

    for nid, node in _oh_nodes.items():
        entry_count = len(node["entries"])
        total_entries += entry_count
        nodes.append({
            "node_id":     node["node_id"],
            "tier":        node["tier"],
            "name":        node["name"],
            "region":      node["region"],
            "entry_count": entry_count,
            "merkle_root": node["merkle_root"],
            "updated_at":  node["updated_at"],
        })

    # 계층별 집계
    tier_summary = {}
    for n in nodes:
        t = n["tier"]
        tier_summary.setdefault(t, {"count": 0, "total_entries": 0})
        tier_summary[t]["count"] += 1
        tier_summary[t]["total_entries"] += n["entry_count"]

    return {
        "nodes":         nodes,
        "total_entries": total_entries,
        "tier_summary":  tier_summary,
        "last_anchor":   last_anchor,
        "node_count":    len(nodes),
        "timestamp":     datetime.utcnow().isoformat(),
    }


@app.get("/openhash/verify/{conv_id}")
async def openhash_verify(conv_id: str, user=Depends(current_user)):
    """
    해당 대화의 OpenHash 등록 검증.
    시뮬레이션: DB 앵커 조회 → verified=true 반환.
    실제 배포 시 각 노드에 독립 검증 요청으로 교체.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM openhash_anchors WHERE conv_id=? ORDER BY created_at DESC LIMIT 1",
        (conv_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {
            "conv_id":  conv_id,
            "verified": False,
            "message":  "앵커 기록 없음. 대화 종료 후 분석을 먼저 실행하세요.",
        }

    row = dict(row)
    propagated = json.loads(row.get("propagated_to", "[]"))

    # 인메모리 노드에서 Merkle 루트 재확인
    node = _oh_nodes.get(row["node_id"], {})
    current_merkle = node.get("merkle_root", "N/A (서버 재시작 후 초기화됨)")

    return {
        "conv_id":         conv_id,
        "verified":        True,
        "anchor_id":       row["anchor_id"],
        "tier":            row["tier"],
        "node_id":         row["node_id"],
        "node_name":       row["node_name"],
        "content_hash":    row["content_hash"],
        "chain_hash":      row["chain_hash"],
        "merkle_root_at_registration": row["merkle_root"],
        "merkle_root_current":         current_merkle,
        "grade":           row["grade"],
        "propagated_to":   propagated,
        "registered_at":   row["created_at"],
        "verification_note": "시뮬레이션 모드: 단일 서버 인메모리 검증. 실제 배포 시 분산 노드 독립 검증(0.34초)으로 교체.",
    }


@app.get("/openhash/pdv/{conv_id}")
async def openhash_pdv_record(conv_id: str, user=Depends(current_user)):
    """PDV Records 조회 (특정 대화)"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM pdv_records WHERE conv_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
        (conv_id, user["sub"])
    ).fetchone()
    conn.close()
    if not row:
        return {"status": "not_found"}
    r = dict(row)
    r["propagated_to"] = json.loads(r.get("propagated_to", "[]"))
    r["legal_refs"]    = json.loads(r.get("legal_refs", "[]"))
    return r


# ══════════════════════════════════════════════════
# ⑫ WebSocket 채팅 (Fast-Path만 실행, 변경 없음)
# ══════════════════════════════════════════════════

@app.websocket("/ws/{conv_id}")
async def websocket_endpoint(conv_id: str, ws: WebSocket, token: str):
    try:
        user = verify_jwt(token)
    except Exception:
        await ws.close(code=4001)
        return

    await manager.connect(conv_id, ws)
    try:
        while True:
            data = await ws.receive_json()

            if data.get("type") == "ping" or not data.get("content", "").strip():
                continue

            content = data.get("content", "").strip()
            msg_id  = str(uuid.uuid4())

            fp       = fast_path_scan(content)
            grade    = fp["grade"]
            keywords = fp["keywords"]

            if grade == "S3":
                await ws.send_json({
                    "type":     "fast_block",
                    "grade":    "S3",
                    "keywords": keywords,
                    "reason":   fp["reason"],
                    "notice":   "보이스피싱 또는 불법 행위 관련 메시지가 차단되었습니다. "
                                "해당 행위는 전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법에 의해 처벌받을 수 있습니다."
                })
                continue

            conn = get_db()
            conn.execute(
                """INSERT INTO messages
                   (msg_id, conv_id, sender_id, content, phase_grade, fast_keywords)
                   VALUES (?,?,?,?,?,?)""",
                (msg_id, conv_id, user["sub"], content, grade,
                 json.dumps(keywords, ensure_ascii=False))
            )
            conn.commit()
            conn.close()

            packet = {
                "type":          "message",
                "msg_id":        msg_id,
                "sender":        user["username"],
                "content":       content,
                "grade":         grade,
                "fast_keywords": keywords,
                "warning":       fp["warning"],
                "fast_reason":   fp["reason"],
                "timestamp":     datetime.utcnow().isoformat()
            }
            await manager.broadcast(conv_id, packet)

            if grade in ("S1", "S2"):
                await ws.send_json({
                    "type":     "fast_warning",
                    "grade":    grade,
                    "keywords": keywords,
                    "reason":   fp["reason"],
                    "notice":   f"주의: '{', '.join(keywords)}' 키워드가 탐지되었습니다. "
                                "대화 종료 시 정밀 분석이 실행됩니다."
                })

    except WebSocketDisconnect:
        manager.disconnect(conv_id, ws)


# ══════════════════════════════════════════════════
# ⑬ 헬스체크
# ══════════════════════════════════════════════════

@app.get("/health")
async def health():
    # 인메모리 노드 현황 간략 포함
    total_entries = sum(len(n["entries"]) for n in _oh_nodes.values())
    return {
        "status":              "ok",
        "time":                datetime.utcnow().isoformat(),
        "version":             "3.0.0",
        "openhash_nodes":      len(_oh_nodes),
        "openhash_entries":    total_entries,
        "deepseek_configured": bool(DEEPSEEK_API_KEY),
    }


# ══════════════════════════════════════════════════
# ⑭ 실행
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gopang_server:app", host="0.0.0.0", port=8000, reload=False)
