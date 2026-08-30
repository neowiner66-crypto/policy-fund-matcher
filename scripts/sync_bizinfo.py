"""기업마당(bizinfo.go.kr) 지원사업정보 오픈API를 호출해 data/announcements.json을 최신 상태로 갱신한다.

사용법:
    python scripts/sync_bizinfo.py

필요조건:
    프로젝트 루트의 .env 파일에 BIZINFO_API_KEY=발급받은인증키 가 있어야 한다.
    (발급: https://www.bizinfo.go.kr/apiList.do → 지원사업정보 API → 사용신청)

동작:
    1. 기업마당 API를 페이지 단위로 호출해 현재 등록된 지원사업 공고를 모두 받아온다.
    2. 우리 announcements.json 스키마(core/matching_engine.py가 기대하는 필드)로 매핑한다.
       분야(searchLclasId 계열)는 자금목적(purpose)·자가진단 카테고리로 러프하게 매핑한다 —
       기계적 매핑이라 완벽하지 않으니, 특정 공고의 매칭이 이상하면 announcements.json에서
       해당 항목만 직접 손봐도 된다 (이 스크립트를 다시 돌리면 그 수정은 덮어써진다).
    3. data/announcements.json을 통째로 교체한다 (기업마당 공고 전용 — 손으로 추가한 정책자금은
       funds_master.json에 있으므로 영향받지 않는다).

주의:
    이 스크립트는 "지금 이 순간 API가 반환하는 공고 스냅샷"으로 파일을 덮어쓴다.
    실행 후 반드시 앱을 재시작(또는 새로고침)해서 반영해야 한다 — Streamlit이 core/ 밑의
    모듈 변경은 자동 반영하지 않는 경우가 있는 것과 달리, data/*.json은 페이지가 매번
    새로 읽으므로 서버 재시작 없이도 다음 새로고침에 반영된다.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OUTPUT_PATH = ROOT / "data" / "announcements.json"

API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
PAGE_UNIT = 100
MAX_PAGES = 20  # 안전장치: 최대 2,000건까지만 (기업마당 전체 현재 공고가 보통 1,500~2,000건 수준)

# 기업마당 분야(대분류) -> 우리 앱의 자금목적 / 자가진단 카테고리로 러프 매핑.
# 완벽한 대응은 아니고, 매칭엔진이 이미 "부합도 낮음" 감점을 두고 있어 틀려도 후보에서
# 완전히 빠지지는 않는다 (CLAUDE.md의 "하드 필터링 최소화" 원칙과 일치).
FIELD_MAP = {
    "금융": {"eligible_purposes": ["운전", "시설"], "relevant_categories": ["경영"]},
    "기술": {"eligible_purposes": ["R&D"], "relevant_categories": ["기술"]},
    "인력": {"eligible_purposes": ["운전"], "relevant_categories": ["고용"]},
    "수출": {"eligible_purposes": ["사업화"], "relevant_categories": ["투자/수출"]},
    "내수": {"eligible_purposes": ["사업화"], "relevant_categories": []},
    "창업": {"eligible_purposes": ["사업화"], "relevant_categories": ["창업"]},
    "경영": {"eligible_purposes": ["운전"], "relevant_categories": ["경영"]},
    "기타": {"eligible_purposes": [], "relevant_categories": []},
}
DEFAULT_FIELD = {"eligible_purposes": [], "relevant_categories": []}


def load_env():
    """.env 파일을 읽어 os.environ에 없는 값만 채워넣는다 (외부 패키지 의존 없이 최소 구현)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def fetch_page(api_key: str, page_index: int) -> dict:
    params = {
        "crtfcKey": api_key,
        "dataType": "json",
        "pageUnit": PAGE_UNIT,
        "pageIndex": page_index,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def fetch_all(api_key: str) -> list:
    """페이지를 넘겨가며 전체 공고를 받아온다 (totCnt만큼, MAX_PAGES 안전장치 적용)."""
    items = []
    total = None
    for page in range(1, MAX_PAGES + 1):
        data = fetch_page(api_key, page)
        page_items = data.get("jsonArray", [])
        if not page_items:
            break
        items.extend(page_items)
        total = page_items[0].get("totCnt")
        if total and len(items) >= int(total):
            break
    return items


def parse_period(reqst_begin_end: str):
    """'2026-08-24 ~ 2026-09-11' 형태를 (start, end)로 분리. 형식이 다르면 (None, None)."""
    if not reqst_begin_end:
        return None, None
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})\s*", reqst_begin_end)
    if m:
        return m.group(1), m.group(2)
    # '20220727 ~ 20220930'처럼 하이픈 없는 옛 포맷 대비
    m = re.match(r"\s*(\d{8})\s*~\s*(\d{8})\s*", reqst_begin_end)
    if m:
        def fmt(d):
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        return fmt(m.group(1)), fmt(m.group(2))
    return None, None  # '상시접수' 등 -> 상시 공고로 취급 (마감일 없음)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def map_item(item: dict) -> dict:
    field = item.get("pldirSportRealmLclasCodeNm", "")
    mapping = FIELD_MAP.get(field, DEFAULT_FIELD)

    jrsd = item.get("jrsdInsttNm", "").strip()
    exc = item.get("excInsttNm", "").strip()
    institution = f"{jrsd} · {exc}" if exc and exc != jrsd else (jrsd or exc or "-")

    start, end = parse_period(item.get("reqstBeginEndDe", ""))
    contact = item.get("refrncNm", "").strip()
    summary = strip_html(item.get("bsnsSumryCn", ""))[:200]

    mapped = {
        "id": item.get("pblancId"),
        "name": item.get("pblancNm", "").strip(),
        "institution": institution,
        "type": f"지원사업 공고 ({field})" if field else "지원사업 공고",
        "kind": "announcement",
        "eligible_purposes": mapping["eligible_purposes"],
        "min_years": 0,
        "region_required": False,
        "relevant_categories": mapping["relevant_categories"],
        "base_score": 25,
        "purpose_bonus": 20,
        "years_bonus": 0,
        "category_weight": 20,
        "limit_text": summary or "공고 원문 참고",
        "receive_text": item.get("reqstMthPapersCn", "").strip() or "공고 원문 참고",
        "note_text": f"문의처: {contact}" if contact else "",
        "application_start": start,
        "application_end": end,
        "source_url": item.get("rceptEngnHmpgUrl") or item.get("pblancUrl") or "",
        "target": item.get("trgetNm", ""),
        # 지역 필터링용 원본 해시태그 보존 (core.matching_engine.filter_by_region이 사용).
        # 지역 관련 해시태그가 하나도 없으면 전국 대상 공고로 취급한다.
        "hashtags": item.get("hashtags", ""),
    }
    # 값이 없는 application_start/end는 아예 키를 빼서 "상시 공고"로 취급되게 한다.
    if not mapped["application_start"]:
        mapped.pop("application_start")
    if not mapped["application_end"]:
        mapped.pop("application_end")
    return mapped


def main():
    load_env()
    api_key = os.environ.get("BIZINFO_API_KEY", "")
    if not api_key or api_key in ("여기에_새_키_붙여넣기", ""):
        print(".env에 BIZINFO_API_KEY가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    print("기업마당 API에서 공고 목록을 가져오는 중...")
    raw_items = fetch_all(api_key)
    print(f"  -> {len(raw_items)}건 수신")

    mapped = [map_item(it) for it in raw_items if it.get("pblancId") and it.get("pblancNm")]

    # 같은 공고ID가 페이지 경계에서 중복 수신될 수 있어 정리
    by_id = {m["id"]: m for m in mapped}
    result = {
        "note": (
            "기업마당(bizinfo.go.kr) 오픈API로 자동 수집된 데이터입니다 "
            "(scripts/sync_bizinfo.py). 수동으로 고친 항목은 이 스크립트를 다시 실행하면 "
            "덮어써지니 주의하세요."
        ),
        "schema_note": (
            "funds_master.json과 동일한 점수 필드를 쓰되, kind: 'announcement', "
            "application_start/application_end(YYYY-MM-DD, 없으면 상시), source_url이 추가됩니다."
        ),
        "synced_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "announcements": list(by_id.values()),
    }

    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"완료: {len(by_id)}건을 {OUTPUT_PATH} 에 저장했습니다.")


if __name__ == "__main__":
    main()
