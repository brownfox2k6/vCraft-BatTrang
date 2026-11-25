"""Integration tests for the vCraft Bat Trang Design System and base layouts."""

from fastapi.testclient import TestClient

from app.core.templating import create_templates


def test_homepage_renders_brand_shell_without_play_cdn(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    html = response.text
    assert "/static/css/app.css" in html
    assert "/static/js/layout.js" in html
    assert "cdn.tailwindcss.com" not in html

    # Brand identity, core public navigation links, account, and primary RFQ CTA.
    assert "vCraft" in html
    assert "Bát Tràng" in html
    for path in (
        "/kham-pha",
        "/xuong",
        "/ban-do",
        "/tin-lang-nghe",
        "/dang-nhap",
        "/yeu-cau-bao-gia/tao",
    ):
        assert f'href="{path}"' in html

    # Mobile navigation control and semantic landmarks.
    assert "<header" in html
    assert "<main" in html
    assert "<footer" in html
    assert 'data-drawer-toggle="mobile-nav"' in html


def test_compiled_stylesheet_exposes_brand_tokens_fonts_and_fluid_typography(
    client: TestClient,
) -> None:
    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")

    css = response.text.lower()
    assert len(css) > 1000

    # Brand palette tokens: cream, cobalt glaze (men lam), terracotta (nau dat).
    assert "#fbf7f0" in css
    assert "#1e4e79" in css
    assert "#8b4513" in css

    # Vietnamese-ready display and body typography plus Fluid Typography clamp().
    assert "lora" in css
    assert "be vietnam pro" in css
    assert "clamp(" in css


def test_workspace_layout_renders_reusable_sidebar_and_shared_design_system() -> None:
    templates = create_templates()
    child_template = templates.env.from_string(
        '{% extends "layouts/workspace.html" %}'
        "{% block workspace_content %}<h1>Điều phối đơn RFQ-026</h1>{% endblock %}"
    )

    html = child_template.render(
        page_title="Điều phối đơn — Ban Quản Lý",
        workspace_role_label="Ban Quản Lý",
        sidebar_items=[
            {"label": "Tổng quan", "href": "/quan-tri", "active": False},
            {"label": "Điều phối đơn", "href": "/quan-tri/dieu-phoi", "active": True},
        ],
    )

    assert "/static/css/app.css" in html
    assert "cdn.tailwindcss.com" not in html
    assert "vCraft" in html
    assert "Bát Tràng" in html
    assert "Ban Quản Lý" in html
    assert "<aside" in html
    assert "<main" in html
    assert 'href="/quan-tri"' in html
    assert 'href="/quan-tri/dieu-phoi"' in html
    assert "Điều phối đơn RFQ-026" in html
    assert 'data-drawer-toggle="workspace-sidebar"' in html
