"""기업정보 / 자금정보 데이터 구조 정의.

Streamlit 화면과 무관한 순수 데이터 구조만 담는다.
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CompanyProfile:
    """기업 기본정보 (① 기업정보입력 화면에서 수집)."""

    name: str = ""
    industry: str = ""
    region: str = ""
    years: float = 0.0
    employees: int = 0
    revenue_eok: float = 0.0  # 억원 단위
    debt_eok: float = 0.0  # 억원 단위
    purpose: str = "운전"  # 운전 / 시설 / R&D / 사업화 / 위기
    needed_amount_eok: float = 0.0
    existing_loans: str = ""


@dataclass
class ChecklistState:
    """55개 자가진단 항목 체크 상태. item_id -> bool."""

    answers: Dict[str, bool] = field(default_factory=dict)

    def checked_count(self) -> int:
        return sum(1 for v in self.answers.values() if v)
