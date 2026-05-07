"""
pdv/vault.py — Private Data Vault (Phase 1 MVP)
Phase 1: SQLite + 평문 저장 (Phase 2에서 AES-256 암호화 추가)
OpenHash: SHA-256 해시 체인으로 위변조 감지
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import aiosqlite

from config import config
from models.message import GopangMessage, AnalysisResult, RiskLevel

logger = logging.getLogger(__name__)

# ── DB 스키마 ────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    message_id  TEXT    NOT NULL UNIQUE,   -- OpenHash 서명 ID
    text        TEXT    NOT NULL,
    risk_level  TEXT    DEFAULT 'NONE',
    confidence  INTEGER DEFAULT 0,
    analysis    TEXT,                       -- JSON
    response    TEXT,
    prev_hash   TEXT    DEFAULT '',         -- 이전 블록 해시 (체인)
    block_hash  TEXT    NOT NULL,           -- 이 블록 해시
    timestamp   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_time
    ON messages (user_id, timestamp DESC);
"""


class PrivateDataVault:
    """
    PDV: 모든 대화를 사용자별로 분리·저장.
    Phase 1: SQLite + OpenHash 해시 체인 (암호화는 Phase 2)
    """

    def __init__(self, db_path: str = config.PDV_DB_PATH):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """DB 초기화 (앱 시작 시 1회)"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        logger.info(f"[PDV] 초기화 완료 — {self._db_path}")

    # ── 저장 ─────────────────────────────────────────────────────────

    async def save(
        self,
        user_id: int,
        text: str,
        analysis: AnalysisResult | None,
        response: str,
    ) -> str:
        """메시지 + 분석 결과 저장. OpenHash 서명 ID 반환."""
        timestamp = datetime.now().isoformat()
        prev_hash = await self._get_last_hash(user_id)

        # OpenHash 블록 해시 생성
        block_content = f"{user_id}|{text}|{timestamp}|{prev_hash}"
        block_hash = hashlib.sha256(block_content.encode()).hexdigest()
        message_id = f"GPG-{user_id}-{block_hash[:12].upper()}"

        # 분석 결과 직렬화
        analysis_json = ""
        risk_level = "NONE"
        confidence = 0
        if analysis:
            risk_level = analysis.risk_level.value
            confidence = analysis.confidence
            analysis_json = json.dumps({
                "risk_level": risk_level,
                "confidence": confidence,
                "risk_summary": analysis.risk_summary,
                "legal_basis": analysis.legal_basis,
                "axiom_basis": analysis.axiom_basis,
                "recommended_action": analysis.recommended_action,
                "fp_codes": [t.fp_code for t in analysis.fp_triggers],
            }, ensure_ascii=False)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO messages
                  (user_id, message_id, text, risk_level, confidence,
                   analysis, response, prev_hash, block_hash, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    user_id, message_id, text, risk_level, confidence,
                    analysis_json, response, prev_hash, block_hash, timestamp,
                ),
            )
            await db.commit()

        logger.debug(f"[PDV] 저장 — {message_id} risk={risk_level}")
        return message_id

    # ── 조회 ─────────────────────────────────────────────────────────

    async def load_context(
        self, user_id: int, limit: int = 10
    ) -> list[dict]:
        """최근 N개 메시지를 LLM 컨텍스트 형식으로 반환"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT text, response, timestamp
                FROM messages
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        # 시간 순으로 정렬 후 컨텍스트 구성
        context: list[dict] = []
        for row in reversed(rows):
            context.append({"role": "user", "content": row["text"]})
            if row["response"]:
                context.append({"role": "assistant", "content": row["response"]})
        return context

    async def load_summary(self, user_id: int) -> str:
        """PDV 요약 (세션 시작 시 컨텍스트 주입용)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN risk_level != 'NONE' THEN 1 ELSE 0 END) as warned,
                       MIN(timestamp) as first_at,
                       MAX(timestamp) as last_at
                FROM messages WHERE user_id = ?
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row or row["total"] == 0:
            return "첫 번째 대화입니다."

        return (
            f"총 {row['total']}개 메시지 / "
            f"경고 발령 {row['warned']}회 / "
            f"최초: {row['first_at'][:10]} / "
            f"최근: {row['last_at'][:10]}"
        )

    async def get_history(
        self, user_id: int, limit: int = 20
    ) -> list[dict]:
        """사용자 대화 이력 조회 (/pdv 명령어용)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT message_id, text, risk_level, confidence,
                       timestamp, block_hash
                FROM messages
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def verify_chain(self, user_id: int) -> bool:
        """OpenHash 체인 무결성 검증"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT user_id, text, timestamp, prev_hash, block_hash
                FROM messages
                WHERE user_id = ?
                ORDER BY timestamp ASC
                """,
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()

        for row in rows:
            expected = hashlib.sha256(
                f"{row['user_id']}|{row['text']}|{row['timestamp']}|{row['prev_hash']}".encode()
            ).hexdigest()
            if expected != row["block_hash"]:
                logger.warning(f"[PDV] 체인 손상 감지 — user_id={user_id}")
                return False
        return True

    # ── 내부 ─────────────────────────────────────────────────────────

    async def _get_last_hash(self, user_id: int) -> str:
        """마지막 블록 해시 조회 (체인 연결용)"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT block_hash FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else ""


# 싱글턴
pdv = PrivateDataVault()
