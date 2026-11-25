"""Integration tests for Light & Dark Mode design tokens, anti-FOUC bootstrap, and toggles."""

from fastapi.testclient import TestClient

from app.core.templating import create_templates


def test_homepage_exposes_theme_toggle_and_anti_fouc_bootstrap(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "data-theme-toggle" in html
    assert 'aria-pressed="false"' in html
    assert 'aria-label="Chế độ giao diện tối"' in html
    assert "/static/js/theme.js" in html
    assert "vcraft-theme" in html
    assert "prefers-color-scheme: dark" in html


def test_workspace_layout_exposes_shared_theme_toggle_and_anti_fouc_bootstrap() -> None:
    templates = create_templates()
    child_template = templates.env.from_string(
        '{% extends "layouts/workspace.html" %}'
        "{% block workspace_content %}<h1>Tổng quan</h1>{% endblock %}"
    )

    html = child_template.render(
        workspace_role_label="Ban Quản lý",
        sidebar_items=[{"label": "Tổng quan", "href": "/quan-tri", "active": True}],
    )

    assert "data-theme-toggle" in html
    assert 'aria-label="Chế độ giao diện tối"' in html
    assert "/static/js/theme.js" in html
    assert "vcraft-theme" in html
    assert "bg-backdrop/" in html


def test_compiled_stylesheet_defines_semantic_surface_and_dark_palette_tokens(
    client: TestClient,
) -> None:
    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    css = response.text.lower()

    # Shared semantic surface, backdrop, and action tokens + Light mode tokens.
    for token in (
        "--color-surface",
        "--color-backdrop",
        "--color-cobalt-action",
        "color-scheme:light",
        "#fbf7f0",
        "#1e4e79",
        "#8b4513",
    ):
        assert token in css

    # Dark mode root override and full warm kiln-charcoal / cobalt palette.
    for dark_token in (
        ":root.dark",
        "color-scheme:dark",
        "#161310",
        "#26211b",
        "#f4efe6",
        "#7ab4e6",
        "#296294",
        "#e29a67",
        "#bfb4a6",
        "#3b332a",
    ):
        assert dark_token in css
