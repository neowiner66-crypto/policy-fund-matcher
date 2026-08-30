"""기능 ① 기업정보 입력 폼 (자가진단 체크리스트).

기본정보 + 55개 자가진단 항목을 입력받아 session_state에 저장하고,
② 매칭 결과 화면으로 넘어가기 위한 입력값을 만든다.

업종·소재지 검색이 입력할 때마다 즉시 필터링되어야 해서(폼 안에서는 제출 전까지
입력이 반영되지 않음) 기본정보 위젯들은 st.form 밖에 둔다. 55개 체크박스만
st.form으로 묶어서, 하나씩 체크할 때마다 전체 페이지가 다시 그려지는 걸 막는다.
"""
import json
from pathlib import Path

import streamlit as st

from core.validators import validate_company_form

st.set_page_config(page_title="기업정보 입력 · 정책자금 매칭 어시스턴트", page_icon="📌", layout="wide")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
with open(DATA_DIR / "checklist_55.json", "r", encoding="utf-8") as f:
    CHECKLIST = json.load(f)
with open(DATA_DIR / "ksic_codes.json", "r", encoding="utf-8") as f:
    KSIC_ITEMS = json.load(f)["items"]
with open(DATA_DIR / "regions.json", "r", encoding="utf-8") as f:
    REGIONS = json.load(f)["sido"]

PURPOSE_OPTIONS = ["운전", "시설", "R&D", "사업화", "위기"]

st.caption("STEP 1 / 3")
st.title("기업정보 입력")
st.write("기본정보와 55개 자가진단 항목을 입력하면, 다음 단계에서 가능성이 높은 정책자금·지원공고 후보를 찾아드립니다.")

company_prev = st.session_state.get("company", {})
checklist_prev = st.session_state.get("checklist_answers", {})

st.subheader("기본정보")

c1, c2 = st.columns(2)
with c1:
    name = st.text_input("기업명 *", value=company_prev.get("name", ""))
with c2:
    st.caption("")  # 레이아웃 균형용 빈 칸

# ── 업종: 키워드로 검색 -> 왼쪽에 선택, 오른쪽에 해당 산업분류코드 표시 ─────────
st.markdown("**업종 \\***")
col_industry, col_code = st.columns([3, 1])
with col_industry:
    industry_query = st.text_input(
        "업종 검색 (키워드 입력 후 목록에서 선택)",
        value="",
        placeholder="예: 금속, 소프트웨어, 음식점, 도매",
        label_visibility="collapsed",
    )
    query = industry_query.strip()
    matches = [it for it in KSIC_ITEMS if query in it["name"]] if query else KSIC_ITEMS

    if not matches:
        st.warning("검색 결과가 없습니다. 다른 키워드로 검색해보세요 (예: '금속', '음식').")
        industry_name, industry_code = "", ""
    else:
        options = [f"[{it['code']}] {it['name']} ({it['level']})" for it in matches]
        prev_name = company_prev.get("industry", "")
        default_index = next((i for i, it in enumerate(matches) if it["name"] == prev_name), 0)
        selected_label = st.selectbox(
            "업종 선택", options, index=min(default_index, len(options) - 1), label_visibility="collapsed"
        )
        selected_item = matches[options.index(selected_label)]
        industry_name, industry_code = selected_item["name"], selected_item["code"]
with col_code:
    st.text_input("산업분류코드", value=industry_code, disabled=True)

st.caption(
    "한국표준산업분류(KSIC) 대분류·중분류 기준입니다. 세세분류까지는 아직 없어 "
    "정확한 업종코드는 사업자등록증을 함께 확인하세요."
)

# ── 사업장 소재지: 시/도 -> 시/군/구 2단 선택 (자유입력으로 인한 오탈자 방지) ──
st.markdown("**사업장 소재지 \\***")
col_sido, col_sigungu = st.columns(2)
with col_sido:
    sido_options = list(REGIONS.keys())
    prev_sido = company_prev.get("region_sido", "")
    sido_index = sido_options.index(prev_sido) if prev_sido in sido_options else 0
    sido = st.selectbox("시/도", sido_options, index=sido_index)
with col_sigungu:
    sigungu_options = REGIONS.get(sido, [])
    prev_sigungu = company_prev.get("region_sigungu", "")
    sigungu_index = sigungu_options.index(prev_sigungu) if prev_sigungu in sigungu_options else 0
    sigungu = st.selectbox("시/군/구", sigungu_options, index=sigungu_index)
region = f"{sido} {sigungu}"

c4, c5, c6 = st.columns(3)
with c4:
    years = st.number_input(
        "업력(년)", min_value=0.0, step=0.5, value=float(company_prev.get("years", 0.0))
    )
with c5:
    employees = st.number_input(
        "상시근로자 수(명)", min_value=0, step=1, value=int(company_prev.get("employees", 0))
    )
with c6:
    revenue_eok = st.number_input(
        "최근 연매출(억원)", min_value=0.0, step=0.5, value=float(company_prev.get("revenue_eok", 0.0))
    )

c7, c8, c9 = st.columns(3)
with c7:
    debt_eok = st.number_input(
        "기존 부채(억원)", min_value=0.0, step=0.5, value=float(company_prev.get("debt_eok", 0.0))
    )
with c8:
    purpose_default = company_prev.get("purpose", PURPOSE_OPTIONS[0])
    purpose = st.selectbox(
        "자금목적 *",
        PURPOSE_OPTIONS,
        index=PURPOSE_OPTIONS.index(purpose_default) if purpose_default in PURPOSE_OPTIONS else 0,
    )
with c9:
    needed_amount_eok = st.number_input(
        "필요자금(억원)", min_value=0.0, step=0.5, value=float(company_prev.get("needed_amount_eok", 0.0))
    )

existing_loans = st.text_area(
    "기존 정책자금·대출 이용 현황 (선택)",
    value=company_prev.get("existing_loans", ""),
    placeholder="예: 202X년 OO은행 시설자금 3억원 이용 중",
)

st.divider()

with st.form("checklist_form"):
    st.subheader("자가진단 체크리스트 (55개 항목)")
    st.caption(
        "해당하는 항목만 체크하세요. 체크 항목이 많다고 자동으로 승인되는 것은 아니며, "
        "다음 단계의 추천 순위 산정에 참고 신호로만 활용됩니다."
    )

    checklist_answers = {}
    for cat in CHECKLIST["categories"]:
        with st.expander(f"{cat['label']} ({len(cat['items'])}개 항목)"):
            for item in cat["items"]:
                checklist_answers[item["id"]] = st.checkbox(
                    item["label"],
                    value=bool(checklist_prev.get(item["id"], False)),
                    key=f"chk_{item['id']}",
                )

    submitted = st.form_submit_button("매칭 결과 보기 →", type="primary")

if submitted:
    company = {
        "name": name.strip(),
        "industry": industry_name,
        "industry_code": industry_code,
        "region": region.strip(),
        "region_sido": sido,
        "region_sigungu": sigungu,
        "years": years,
        "employees": employees,
        "revenue_eok": revenue_eok,
        "debt_eok": debt_eok,
        "purpose": purpose,
        "needed_amount_eok": needed_amount_eok,
        "existing_loans": existing_loans.strip(),
    }

    errors = validate_company_form(company)
    if errors:
        for e in errors:
            st.error(e)
    else:
        st.session_state["company"] = company
        st.session_state["checklist_answers"] = checklist_answers
        st.switch_page("pages/2_매칭결과.py")
