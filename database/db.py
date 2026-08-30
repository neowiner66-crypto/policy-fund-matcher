"""SQLite 연결/초기화.

MVP 단계에서는 암호화 없이 로컬 파일로 저장한다.
실제 서비스 전환 시 사업자등록번호·재무제표 등 민감 컬럼은 반드시
암호화 저장(예: SQLCipher, 애플리케이션 레벨 암호화)으로 교체할 것
(CLAUDE.md 6절 리스크·컴플라이언스 원칙 참고).
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("POLICY_FUND_DB_PATH", str(BASE_DIR / "database" / "policy_fund.db"))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


def save_consultation(company: dict, checklist_checked_count: int, selected_fund: dict | None) -> int:
    """상담 결과(기업정보 + 선택한 자금)를 저장하고 consultation id를 반환."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO companies (name, industry, region, years, employees, revenue_eok, debt_eok)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company.get("name"),
                company.get("industry"),
                company.get("region"),
                company.get("years"),
                company.get("employees"),
                company.get("revenue_eok"),
                company.get("debt_eok"),
            ),
        )
        company_id = cur.lastrowid

        cur = conn.execute(
            """
            INSERT INTO consultations (
                company_id, purpose, needed_amount_eok, checklist_checked_count,
                selected_fund_id, selected_fund_name, selected_fund_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                company.get("purpose"),
                company.get("needed_amount_eok"),
                checklist_checked_count,
                (selected_fund or {}).get("id"),
                (selected_fund or {}).get("name"),
                (selected_fund or {}).get("score"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
