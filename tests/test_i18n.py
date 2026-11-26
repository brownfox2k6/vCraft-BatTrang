"""Tests for bilingual i18n formatting, dynamic fallback, catalog, and language switching."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.templating import create_templates
from app.i18n import LANG_COOKIE_NAME
from app.i18n.catalog import load_catalog, translate
from app.i18n.fallback import localized_field, pick_localized
from app.i18n.formatting import format_currency, format_date, format_datetime


@pytest.mark.parametrize(
    ("amount", "lang", "expected"),
    [
        (48000, "vi", "48.000 đ"),
        (48000, "en", "48,000 VND"),
        (Decimal("1250000"), "vi", "1.250.000 đ"),
        (Decimal("1250000.60"), "en", "1,250,001 VND"),
        (0, "vi", "0 đ"),
        (0, "en", "0 VND"),
        (-48000, "vi", "-48.000 đ"),
        (-48000, "en", "-48,000 VND"),
    ],
)
def test_format_currency_matches_locale_conventions(
    amount: int | float | Decimal,
    lang: str,
    expected: str,
) -> None:
    assert format_currency(amount, lang) == expected


def test_format_date_matches_locale_conventions() -> None:
    target = date(2026, 11, 26)

    assert format_date(target, "vi") == "26/11/2026"
    assert format_date(target, "en") == "Nov 26, 2026"


def test_format_datetime_converts_timezone_aware_values_to_ho_chi_minh() -> None:
    utc_dt = datetime(2026, 11, 26, 1, 30, tzinfo=UTC)
    naive_dt = datetime(2026, 11, 26, 8, 30)

    assert format_datetime(utc_dt, "vi") == "26/11/2026 08:30"
    assert format_datetime(utc_dt, "en") == "Nov 26, 2026, 08:30"
    assert format_datetime(naive_dt, "vi") == "26/11/2026 08:30"
    assert format_datetime(naive_dt, "en") == "Nov 26, 2026, 08:30"


@dataclass(frozen=True)
class _SampleWorkshop:
    name_vi: str
    name_en: str | None


@pytest.mark.parametrize(
    ("vi_text", "en_text", "lang", "expected"),
    [
        ("Xưởng gốm Minh Long", "Minh Long Ceramic Workshop", "en", "Minh Long Ceramic Workshop"),
        ("Xưởng gốm Minh Long", "Minh Long Ceramic Workshop", "vi", "Xưởng gốm Minh Long"),
        ("Xưởng gốm Minh Long", None, "en", "Xưởng gốm Minh Long"),
        ("Xưởng gốm Minh Long", "", "en", "Xưởng gốm Minh Long"),
        ("Xưởng gốm Minh Long", "   \t\n ", "en", "Xưởng gốm Minh Long"),
        (None, "English Only Fallback", "vi", "English Only Fallback"),
        (None, None, "en", ""),
    ],
)
def test_pick_localized_prefers_selected_lang_and_falls_back_to_vi(
    vi_text: str | None,
    en_text: str | None,
    lang: str,
    expected: str,
) -> None:
    assert pick_localized(vi_text, en_text, lang) == expected


def test_localized_field_reads_suffix_columns_from_objects_and_dicts() -> None:
    workshop_full = _SampleWorkshop(
        name_vi="Xưởng Men Lam Cổ",
        name_en="Heritage Cobalt Glaze Workshop",
    )
    workshop_missing_en = _SampleWorkshop(name_vi="Xưởng Đất Nung", name_en="  ")
    product_dict = {"title_vi": "Ấm trà men rạn", "title_en": None}

    assert localized_field(workshop_full, "name", "en") == "Heritage Cobalt Glaze Workshop"
    assert localized_field(workshop_full, "name", "vi") == "Xưởng Men Lam Cổ"
    assert localized_field(workshop_missing_en, "name", "en") == "Xưởng Đất Nung"
    assert localized_field(product_dict, "title", "en") == "Ấm trà men rạn"


def test_translate_looks_up_dot_keys_and_keeps_vi_and_en_catalogs_in_sync() -> None:
    assert translate("nav.explore", "vi") == "Khám phá"
    assert translate("nav.explore", "en") == "Explore"
    assert translate("missing.translation.key", "en") == "missing.translation.key"

    vi_catalog = load_catalog("vi")
    en_catalog = load_catalog("en")
    assert set(vi_catalog.keys()) == set(en_catalog.keys())
    assert all(value.strip() for value in vi_catalog.values())
    assert all(value.strip() for value in en_catalog.values())


def test_homepage_defaults_to_vi_and_switches_to_en_via_lang_cookie(client: TestClient) -> None:
    initial = client.get("/")
    assert initial.status_code == 200
    assert '<html lang="vi"' in initial.text
    assert "Khám phá" in initial.text
    assert "Bát Tràng, chuyện đất hóa tinh hoa" in initial.text
    assert 'action="/lang"' in initial.text

    switch_response = client.post(
        "/lang",
        data={"lang": "en", "next": "/?tab=featured"},
        follow_redirects=False,
    )
    assert switch_response.status_code == 303
    assert switch_response.headers["location"] == "/?tab=featured"
    set_cookie = switch_response.headers.get("set-cookie", "")
    assert f"{LANG_COOKIE_NAME}=en" in set_cookie
    assert "Max-Age=" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    english_home = client.get("/")
    assert english_home.status_code == 200
    assert '<html lang="en"' in english_home.text
    assert "Explore" in english_home.text
    assert "Request a Quote" in english_home.text
    assert "Bát Tràng, where clay becomes craft" in english_home.text
    assert "Meet the Artisans" in english_home.text

    back_to_vi = client.post("/lang", data={"lang": "vi", "next": "/"}, follow_redirects=False)
    assert back_to_vi.status_code == 303
    vietnamese_home = client.get("/")
    assert '<html lang="vi"' in vietnamese_home.text
    assert "Yêu cầu báo giá" in vietnamese_home.text


@pytest.mark.parametrize(
    "unsafe_next",
    [
        "https://evil.example/phish",
        "//evil.example/phish",
        "javascript:alert(1)",
        "/\\evil.example",
    ],
)
def test_lang_endpoint_rejects_unsafe_redirect_targets(
    client: TestClient,
    unsafe_next: str,
) -> None:
    response = client.post(
        "/lang",
        data={"lang": "en", "next": unsafe_next},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_lang_endpoint_falls_back_to_same_origin_referer_when_next_is_empty(
    client: TestClient,
) -> None:
    response = client.post(
        "/lang",
        data={"lang": "en", "next": "   "},
        headers={"referer": "http://testserver/kham-pha?glaze=cobalt"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/kham-pha?glaze=cobalt"


def test_invalid_lang_cookie_falls_back_to_vi(client: TestClient) -> None:
    client.cookies.set(LANG_COOKIE_NAME, "fr")
    response = client.get("/")
    assert response.status_code == 200
    assert '<html lang="vi"' in response.text
    assert "Khám phá" in response.text


def test_workspace_layout_and_jinja_helpers_render_in_selected_language() -> None:
    templates = create_templates()
    child = templates.env.from_string(
        '{% extends "layouts/workspace.html" %}'
        "{% block workspace_content %}"
        "<p>{{ localize(workshop, 'name') }}</p>"
        "<p>{{ 48000 | format_currency }}</p>"
        "<p>{{ sample_date | format_date }}</p>"
        "<p>{{ sample_dt | format_datetime }}</p>"
        "{% endblock %}"
    )
    workshop = _SampleWorkshop(name_vi="Xưởng Cổ", name_en=None)
    html_en = child.render(
        lang="en",
        workshop=workshop,
        sample_date=date(2026, 11, 26),
        sample_dt=datetime(2026, 11, 26, 1, 30, tzinfo=UTC),
        sidebar_items=[],
    )
    assert '<html lang="en"' in html_en
    assert "Back to Exhibition" in html_en
    assert 'action="/lang"' in html_en
    assert "Xưởng Cổ" in html_en
    assert "48,000 VND" in html_en
    assert "Nov 26, 2026" in html_en
    assert "Nov 26, 2026, 08:30" in html_en
