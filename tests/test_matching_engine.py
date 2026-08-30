"""매칭 로직 단위테스트. 오추천 시 신뢰도에 직접 영향을 주는 부분이라 최소한이라도 검증한다."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.matching_engine import calculate_matches, merge_active_sources, filter_by_region  # noqa: E402

DATA_DIR = ROOT / "data"


def load_data():
    with open(DATA_DIR / "funds_master.json", "r", encoding="utf-8") as f:
        funds = json.load(f)
    with open(DATA_DIR / "checklist_55.json", "r", encoding="utf-8") as f:
        checklist = json.load(f)
    return funds, checklist


def load_announcements():
    with open(DATA_DIR / "announcements.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_results_sorted_descending_by_score():
    funds, checklist = load_data()
    company = {
        "name": "테스트기업",
        "industry": "기계·장비 제조",
        "region": "충북",
        "years": 12,
        "revenue_eok": 35,
        "debt_eok": 6,
        "purpose": "시설",
        "needed_amount_eok": 5,
    }
    results = calculate_matches(company, {}, funds, checklist)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert len(results) == len(funds["funds"])


def test_every_fund_has_reasons():
    funds, checklist = load_data()
    company = {"name": "x", "industry": "y", "region": "서울", "years": 3, "purpose": "운전", "debt_eok": 0}
    results = calculate_matches(company, {}, funds, checklist)
    for r in results:
        assert len(r["reasons"]) >= 1


def test_checklist_checkmarks_increase_relevant_fund_score():
    funds, checklist = load_data()
    company = {"name": "x", "industry": "y", "region": "서울", "years": 10, "purpose": "R&D", "debt_eok": 0}

    base = calculate_matches(company, {}, funds, checklist)
    base_kibo = next(r for r in base if r["fund"]["id"] == "kibo")["score"]

    tech_items = next(c for c in checklist["categories"] if c["key"] == "기술")["items"]
    all_tech_checked = {item["id"]: True for item in tech_items}
    boosted = calculate_matches(company, all_tech_checked, funds, checklist)
    boosted_kibo = next(r for r in boosted if r["fund"]["id"] == "kibo")["score"]

    assert boosted_kibo >= base_kibo


def test_score_is_clipped_between_0_and_100():
    funds, checklist = load_data()
    company = {"name": "x", "industry": "y", "region": "", "years": 0, "purpose": "사회적경제무관", "debt_eok": 0}
    results = calculate_matches(company, {}, funds, checklist)
    for r in results:
        assert 0 <= r["score"] <= 100


def test_merge_active_sources_excludes_expired_announcements():
    funds, _ = load_data()
    announcements = {
        "announcements": [
            {"id": "expired", "name": "마감된 공고", "kind": "announcement", "application_end": "2020-01-01"},
            {"id": "active", "name": "진행중 공고", "kind": "announcement", "application_end": "2999-12-31"},
            {"id": "no_deadline", "name": "상시 공고", "kind": "announcement"},
        ]
    }
    combined = merge_active_sources(funds, announcements, today=date(2026, 8, 26))
    ids = [f["id"] for f in combined["funds"]]

    assert "expired" not in ids
    assert "active" in ids
    assert "no_deadline" in ids
    # 정책자금 5건 + 살아있는 공고 2건
    assert len(ids) == len(funds["funds"]) + 2


def test_merge_active_sources_with_real_announcements_file_has_no_duplicate_ids():
    funds, _ = load_data()
    announcements = load_announcements()
    combined = merge_active_sources(funds, announcements, today=date(2026, 8, 26))
    ids = [f["id"] for f in combined["funds"]]
    assert len(ids) == len(set(ids))


def test_announcement_reasons_include_application_deadline():
    # 실제 announcements.json은 기업마당 API로 수시 갱신되고, 상시접수(마감일 없음) 공고도
    # 섞여 있어 "모든 공고에 접수기간이 있다"는 가정이 항상 성립하진 않는다.
    # 그래서 마감일이 있는 경우의 동작만 고정 데이터로 검증한다.
    funds, checklist = load_data()
    announcements = {
        "announcements": [
            {
                "id": "with_deadline",
                "name": "마감일 있는 공고",
                "kind": "announcement",
                "eligible_purposes": ["시설"],
                "application_end": "2999-12-31",
            }
        ]
    }
    combined = merge_active_sources(funds, announcements, today=date(2026, 8, 26))
    company = {"name": "x", "industry": "y", "region": "서울", "years": 5, "purpose": "시설", "debt_eok": 0}

    results = calculate_matches(company, {}, combined, checklist)
    r = next(r for r in results if r["fund"]["id"] == "with_deadline")
    assert any("접수기간" in reason for reason in r["reasons"])


def test_real_announcements_file_loads_and_has_expected_fields():
    """scripts/sync_bizinfo.py가 만든 실제 데이터 파일이 매칭엔진이 기대하는 필수 필드를 갖추는지 확인."""
    announcements = load_announcements()
    items = announcements.get("announcements", [])
    assert items, "announcements.json에 최소 1건 이상 있어야 한다"
    for item in items[:50]:  # 전체(수천건) 대신 앞부분만 표본 검사 — 테스트 속도 유지
        assert item.get("id")
        assert item.get("name")
        assert item.get("kind") == "announcement"


def test_include_expired_true_adds_back_expired_announcements_marked():
    funds, _ = load_data()
    announcements = {
        "announcements": [
            {"id": "expired", "name": "마감된 공고", "kind": "announcement", "application_end": "2020-01-01"},
            {"id": "active", "name": "진행중 공고", "kind": "announcement", "application_end": "2999-12-31"},
        ]
    }
    default = merge_active_sources(funds, announcements, today=date(2026, 8, 26))
    with_expired = merge_active_sources(
        funds, announcements, today=date(2026, 8, 26), include_expired=True
    )

    assert "expired" not in [f["id"] for f in default["funds"]]

    by_id = {f["id"]: f for f in with_expired["funds"]}
    assert "expired" in by_id
    assert by_id["expired"]["is_expired"] is True
    assert by_id["active"]["is_expired"] is False


def test_expired_announcements_never_outrank_active_ones_regardless_of_score():
    funds, checklist = load_data()
    announcements = {
        "announcements": [
            # 마감됐지만 다른 조건은 만점에 가깝게 유리한 공고
            {
                "id": "expired_high_score",
                "name": "마감된 고득점 공고",
                "kind": "announcement",
                "eligible_purposes": ["운전"],
                "min_years": 0,
                "region_required": False,
                "relevant_categories": [],
                "base_score": 90,
                "purpose_bonus": 10,
                "application_end": "2020-01-01",
            },
            # 진행중이지만 점수가 낮은 공고
            {
                "id": "active_low_score",
                "name": "진행중 저득점 공고",
                "kind": "announcement",
                "eligible_purposes": [],
                "min_years": 0,
                "region_required": False,
                "relevant_categories": [],
                "base_score": 1,
                "application_end": "2999-12-31",
            },
        ]
    }
    combined = merge_active_sources(funds, announcements, today=date(2026, 8, 26), include_expired=True)
    company = {"name": "x", "industry": "y", "region": "", "years": 0, "purpose": "운전", "debt_eok": 0}
    results = calculate_matches(company, {}, combined, checklist)

    ids_in_order = [r["fund"]["id"] for r in results]
    assert ids_in_order.index("active_low_score") < ids_in_order.index("expired_high_score")


def _region_fixture():
    return {
        "funds": [
            {"id": "policy_fund_1", "kind": "policy_fund"},
            {"id": "nationwide_all_tags", "kind": "announcement", "hashtags": "서울,부산,대구,인천,전남광주,대전,울산,세종,경기,강원,충북,충남,전북,경북,경남,제주"},
            {"id": "no_region_tag", "kind": "announcement", "hashtags": "기술,2026,중소기업"},
            {"id": "chungbuk_only", "kind": "announcement", "hashtags": "충북,경영"},
            {"id": "busan_only", "kind": "announcement", "hashtags": "부산,수출"},
        ]
    }


def test_filter_by_region_keeps_policy_funds_regardless_of_sido():
    filtered = filter_by_region(_region_fixture(), "충북")
    ids = [f["id"] for f in filtered["funds"]]
    assert "policy_fund_1" in ids


def test_filter_by_region_keeps_nationwide_and_matching_region_excludes_others():
    filtered = filter_by_region(_region_fixture(), "충북")
    ids = {f["id"] for f in filtered["funds"]}
    assert "nationwide_all_tags" in ids  # 모든 지역 태그 -> 전국 공고
    assert "no_region_tag" in ids  # 지역 태그 자체가 없음 -> 전국 취급(과도한 배제 방지)
    assert "chungbuk_only" in ids  # 사용자 지역과 일치
    assert "busan_only" not in ids  # 다른 지역 전용 -> 제외


def test_filter_by_region_without_sido_returns_everything_unchanged():
    data = _region_fixture()
    filtered = filter_by_region(data, None)
    assert filtered == data


def test_industry_keyword_match_gives_announcement_a_bonus_and_reason():
    funds, checklist = load_data()
    announcements = {
        "announcements": [
            {
                "id": "metal_industry_support",
                "name": "금속가공제품 제조업 특화 지원사업",
                "kind": "announcement",
                "eligible_purposes": ["운전"],
                "base_score": 30,
                "hashtags": "금속가공,제조업",
                "application_end": "2999-12-31",
            }
        ]
    }
    combined = merge_active_sources(funds, announcements, today=date(2026, 8, 26))
    company_match = {"name": "x", "industry": "금속가공제품 제조업", "region": "서울", "years": 5, "purpose": "운전", "debt_eok": 0}
    company_nomatch = {"name": "x", "industry": "소프트웨어 개발업", "region": "서울", "years": 5, "purpose": "운전", "debt_eok": 0}

    r_match = next(
        r for r in calculate_matches(company_match, {}, combined, checklist) if r["fund"]["id"] == "metal_industry_support"
    )
    r_nomatch = next(
        r for r in calculate_matches(company_nomatch, {}, combined, checklist) if r["fund"]["id"] == "metal_industry_support"
    )

    assert r_match["score"] > r_nomatch["score"]
    assert any("업종" in reason for reason in r_match["reasons"])


if __name__ == "__main__":
    test_results_sorted_descending_by_score()
    test_every_fund_has_reasons()
    test_checklist_checkmarks_increase_relevant_fund_score()
    test_score_is_clipped_between_0_and_100()
    test_merge_active_sources_excludes_expired_announcements()
    test_merge_active_sources_with_real_announcements_file_has_no_duplicate_ids()
    test_announcement_reasons_include_application_deadline()
    test_real_announcements_file_loads_and_has_expected_fields()
    test_include_expired_true_adds_back_expired_announcements_marked()
    test_expired_announcements_never_outrank_active_ones_regardless_of_score()
    test_filter_by_region_keeps_policy_funds_regardless_of_sido()
    test_filter_by_region_keeps_nationwide_and_matching_region_excludes_others()
    test_filter_by_region_without_sido_returns_everything_unchanged()
    test_industry_keyword_match_gives_announcement_a_bonus_and_reason()
    print("all tests passed")
