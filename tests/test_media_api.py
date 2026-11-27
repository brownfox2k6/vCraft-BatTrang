"""Integration tests for the multi-image WebP upload pipeline, media serving, and responsive UI."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.templating import create_templates
from app.i18n import LANG_COOKIE_NAME
from app.models.media import MediaAsset
from tests.conftest import ClientFactory


def _make_image_bytes(
    *,
    size: tuple[int, int],
    fmt: str = "JPEG",
    mode: str = "RGB",
    color: tuple[int, ...] = (30, 78, 121),
    exif_bytes: bytes | None = None,
) -> bytes:
    img = Image.new(mode, size, color=color)
    buf = io.BytesIO()
    if exif_bytes is not None:
        img.save(buf, format=fmt, exif=exif_bytes)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def _register_and_login(client: TestClient, email: str = "uploader@battrang.vn") -> str:
    resp = client.post(
        "/api/auth/register",
        json={
            "full_name": "Nghệ nhân An",
            "email": email,
            "password": "ValidPassword1",
        },
    )
    assert resp.status_code == 201
    return str(resp.json()["data"]["user"]["id"])


def test_media_upload_requires_authentication_and_csrf(
    make_client: ClientFactory,
    tmp_path: Path,
) -> None:
    png_bytes = _make_image_bytes(size=(200, 200), fmt="PNG")

    with make_client(media_root=str(tmp_path)) as anon_client:
        resp = anon_client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[("files", ("vase.png", png_bytes, "image/png"))],
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    with make_client(auto_csrf=False, media_root=str(tmp_path)) as raw_client:
        resp = raw_client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[("files", ("vase.png", png_bytes, "image/png"))],
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_INVALID"


def test_media_upload_generates_three_webp_variants_preserving_ratio_and_no_upscale(
    make_client: ClientFactory,
    clean_auth_db: str,
    tmp_path: Path,
) -> None:
    large_jpeg = _make_image_bytes(size=(2400, 1600), fmt="JPEG")
    small_rgba_png = _make_image_bytes(
        size=(300, 200),
        fmt="PNG",
        mode="RGBA",
        color=(30, 78, 121, 180),
    )

    with make_client(media_root=str(tmp_path)) as client:
        user_id = _register_and_login(client)
        resp = client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[
                ("files", ("cobalt_vase.jpg", large_jpeg, "image/jpeg")),
                ("files", ("stamp.png", small_rgba_png, "image/png")),
            ],
        )
        assert resp.status_code == 201
        payload = resp.json()
        assert payload["error"] is None
        items = payload["data"]
        assert len(items) == 2

        first = items[0]
        assert first["category"] == "product"
        assert first["width"] == 1600
        assert first["height"] == 1067
        assert first["thumb_url"].startswith("/media/product/")
        assert first["medium_url"].endswith("/medium.webp")
        assert first["large_url"].endswith("/large.webp")

        # Verify actual WebP files served via GET /media/... with immutable cache header
        for url, expected_size in (
            (first["thumb_url"], (400, 267)),
            (first["medium_url"], (960, 640)),
            (first["large_url"], (1600, 1067)),
        ):
            media_resp = client.get(url)
            assert media_resp.status_code == 200
            assert media_resp.headers["content-type"].startswith("image/webp")
            assert media_resp.headers["cache-control"] == "public, max-age=31536000, immutable"
            with Image.open(io.BytesIO(media_resp.content)) as saved:
                assert saved.format == "WEBP"
                assert saved.size == expected_size

        # Small RGBA PNG must not be upscaled and must preserve alpha
        second = items[1]
        assert second["width"] == 300
        assert second["height"] == 200
        small_large = client.get(second["large_url"])
        assert small_large.status_code == 200
        with Image.open(io.BytesIO(small_large.content)) as saved_small:
            assert saved_small.size == (300, 200)
            assert "A" in saved_small.getbands()

    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            rows = list(db.scalars(select(MediaAsset)).all())
            assert len(rows) == 2
            assert all(str(row.owner_user_id) == user_id for row in rows)
            assert all(row.size_bytes > 0 for row in rows)
    finally:
        engine.dispose()


def test_media_upload_transposes_exif_orientation_and_strips_all_exif_metadata(
    make_client: ClientFactory,
    tmp_path: Path,
) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: Rotate 90 CW
    exif[0x010F] = "Canon"  # Make
    exif[0x0110] = "EOS R5"  # Model
    rotated_jpeg = _make_image_bytes(size=(1200, 600), fmt="JPEG", exif_bytes=exif.tobytes())

    with make_client(media_root=str(tmp_path)) as client:
        _register_and_login(client, email="exif@battrang.vn")
        resp = client.post(
            "/api/media/upload",
            data={"category": "workshop"},
            files=[("files", ("kiln.jpg", rotated_jpeg, "image/jpeg"))],
        )
        assert resp.status_code == 201
        item = resp.json()["data"][0]
        # 1200x600 rotated 90 CW becomes 600x1200
        assert item["width"] == 600
        assert item["height"] == 1200

        large_resp = client.get(item["large_url"])
        assert large_resp.status_code == 200
        with Image.open(io.BytesIO(large_resp.content)) as saved:
            assert saved.size == (600, 1200)
            assert len(saved.getexif()) == 0
            assert "exif" not in saved.info
            assert "icc_profile" not in saved.info


def test_media_upload_accepts_webp_input(
    make_client: ClientFactory,
    tmp_path: Path,
) -> None:
    webp_bytes = _make_image_bytes(size=(800, 600), fmt="WEBP")

    with make_client(media_root=str(tmp_path)) as client:
        _register_and_login(client, email="webp@battrang.vn")
        resp = client.post(
            "/api/media/upload",
            data={"category": "milestone"},
            files=[("files", ("glaze.webp", webp_bytes, "image/webp"))],
        )
        assert resp.status_code == 201
        item = resp.json()["data"][0]
        assert item["category"] == "milestone"
        assert item["width"] == 800
        assert item["height"] == 600


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_media_upload_rejects_fake_formats_oversized_and_too_many_files(
    make_client: ClientFactory,
    tmp_path: Path,
    lang: str,
) -> None:
    svg_spoof = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    valid_png = _make_image_bytes(size=(120, 120), fmt="PNG")

    with make_client(
        media_root=str(tmp_path),
        media_max_bytes=2048,
        media_max_files_per_request=2,
    ) as client:
        _register_and_login(client, email=f"reject-{lang}@battrang.vn")
        client.cookies.set(LANG_COOKIE_NAME, lang)

        # Spoofed .png containing SVG -> 422 MEDIA_INVALID_FORMAT
        fake_resp = client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[("files", ("fake.png", svg_spoof, "image/png"))],
        )
        assert fake_resp.status_code == 422
        assert fake_resp.json()["error"]["code"] == "MEDIA_INVALID_FORMAT"
        assert fake_resp.json()["error"]["message"] != ""

        # Oversized file -> 413 MEDIA_TOO_LARGE
        oversized = _make_image_bytes(size=(1000, 1000), fmt="PNG")
        assert len(oversized) > 2048
        big_resp = client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[("files", ("big.png", oversized, "image/png"))],
        )
        assert big_resp.status_code == 413
        assert big_resp.json()["error"]["code"] == "MEDIA_TOO_LARGE"

        # Too many files (> 2) -> 422 MEDIA_TOO_MANY_FILES
        many_resp = client.post(
            "/api/media/upload",
            data={"category": "product"},
            files=[
                ("files", ("a.png", valid_png, "image/png")),
                ("files", ("b.png", valid_png, "image/png")),
                ("files", ("c.png", valid_png, "image/png")),
            ],
        )
        assert many_resp.status_code == 422
        assert many_resp.json()["error"]["code"] == "MEDIA_TOO_MANY_FILES"

        # Invalid category -> 422 MEDIA_INVALID_CATEGORY
        bad_cat = client.post(
            "/api/media/upload",
            data={"category": "unknown_bucket"},
            files=[("files", ("a.png", valid_png, "image/png"))],
        )
        assert bad_cat.status_code == 422
        assert bad_cat.json()["error"]["code"] == "MEDIA_INVALID_CATEGORY"


def test_media_serving_blocks_path_traversal_and_missing_files(
    make_client: ClientFactory,
    tmp_path: Path,
) -> None:
    secret_file = tmp_path.parent / "outside_secret.txt"
    secret_file.write_text("not-media", encoding="utf-8")

    with make_client(media_root=str(tmp_path)) as client:
        for bad_path in (
            "/media/../outside_secret.txt",
            "/media/..%2Foutside_secret.txt",
            "/media/product/does-not-exist/thumb.webp",
        ):
            resp = client.get(bad_path)
            assert resp.status_code == 404


def test_media_upload_cleans_up_files_if_db_commit_fails(
    make_client: ClientFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.repositories.media_repository import MediaRepository

    valid_png = _make_image_bytes(size=(200, 200), fmt="PNG")

    with make_client(media_root=str(tmp_path)) as client:
        _register_and_login(client, email="cleanup@battrang.vn")

        def _boom(self: MediaRepository) -> None:
            raise RuntimeError("simulated db commit failure")

        monkeypatch.setattr(MediaRepository, "commit", _boom)

        with pytest.raises(RuntimeError, match="simulated db commit failure"):
            client.post(
                "/api/media/upload",
                data={"category": "product"},
                files=[("files", ("vase.png", valid_png, "image/png"))],
            )

    leftover_files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert leftover_files == []


def test_responsive_image_partial_and_media_uploader_js_module(client: TestClient) -> None:
    templates = create_templates()
    tmpl = templates.env.from_string('{% include "partials/responsive_image.html" %}')
    html = tmpl.render(
        thumb_url="/media/product/abc/thumb.webp",
        medium_url="/media/product/abc/medium.webp",
        large_url="/media/product/abc/large.webp",
        alt="Bình men lam Bát Tràng",
        css_class="w-full rounded-lg",
    )
    assert 'src="/media/product/abc/medium.webp"' in html
    assert "/media/product/abc/thumb.webp 400w" in html
    assert "/media/product/abc/medium.webp 960w" in html
    assert "/media/product/abc/large.webp 1600w" in html
    assert 'loading="lazy"' in html
    assert 'decoding="async"' in html
    assert 'alt="Bình men lam Bát Tràng"' in html

    js_resp = client.get("/static/js/media_uploader.js")
    assert js_resp.status_code == 200
    assert "./api.js" in js_resp.text
    assert "FormData" in js_resp.text
    assert "createObjectURL" in js_resp.text
    assert "revokeObjectURL" in js_resp.text
