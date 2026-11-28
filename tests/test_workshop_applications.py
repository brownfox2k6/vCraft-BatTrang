"""Integration tests for public household workshop applications (Issue #7)."""

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import Argon2PasswordHasher
from app.core.slugs import generate_unique_slug, slugify_vi
from app.i18n import LANG_COOKIE_NAME
from app.models.audit import AuditLog
from app.models.auth import User, UserRole
from app.models.media import MediaAsset
from app.models.workshop import WorkshopApplication, WorkshopApplicationStatus
from app.services.audit_service import AuditAction
from tests.conftest import ClientFactory, MutableClock


def _make_png_bytes(size: tuple[int, int] = (200, 150)) -> bytes:
    img = Image.new("RGB", size, color=(30, 78, 121))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload_public_media(client: TestClient, *, category: str) -> str:
    resp = client.post(
        "/api/workshop-applications/media",
        data={"category": category},
        files=[("files", (f"{category}.png", _make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 201
    return str(resp.json()["data"][0]["id"])


def test_slugify_vi_and_generate_unique_slug_handle_vietnamese_and_collisions() -> None:
    assert slugify_vi("Xưởng Gốm Men Lam Đồ Cổ — Bát Tràng!") == "xuong-gom-men-lam-do-co-bat-trang"
    assert slugify_vi("Đất Nung Đỏ") == "dat-nung-do"

    taken = {"xuong-minh-long", "xuong-minh-long-2"}
    assert generate_unique_slug("Xưởng Minh Long", lambda s: s in taken) == "xuong-minh-long-3"


def test_workshop_apply_page_renders_bilingual_form_and_redirects_active_artisan(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    with make_client() as client:
        vi_resp = client.get("/dang-ky-xuong")
        assert vi_resp.status_code == 200
        vi_plain = vi_resp.text.replace("\u00a0", " ")
        assert "Xã Bát Tràng" in vi_plain
        assert 'id="workshop-coord-picker"' in vi_resp.text
        assert 'name="opening_time"' in vi_resp.text
        assert 'name="closing_time"' in vi_resp.text
        assert 'class="form-required"' in vi_resp.text
        assert "tùy chọn" not in vi_plain.lower()
        assert "/static/js/media_uploader.js" in vi_resp.text
        assert "/static/js/workshop_apply.js" in vi_resp.text

        client.cookies.set(LANG_COOKIE_NAME, "en")
        en_resp = client.get("/dang-ky-xuong")
        assert en_resp.status_code == 200
        en_plain = en_resp.text.replace("\u00a0", " ")
        assert "Bát Tràng Commune" in en_plain
        assert 'name="opening_time"' in en_resp.text
        assert 'name="closing_time"' in en_resp.text
        assert 'class="form-required"' in en_resp.text
        assert "optional" not in en_plain.lower()

    # Seed active Artisan -> GET /dang-ky-xuong redirects 303 to /nghe-nhan
    hasher = Argon2PasswordHasher()
    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            db.add(
                User(
                    email="active-artisan@battrang.vn",
                    full_name="Nghệ nhân Lan",
                    password_hash=hasher.hash("ValidPassword1"),
                    role=UserRole.ARTISAN.value,
                    is_active=True,
                )
            )
            db.commit()
    finally:
        engine.dispose()

    with make_client() as artisan_client:
        login_resp = artisan_client.post(
            "/api/auth/login",
            json={"email": "active-artisan@battrang.vn", "password": "ValidPassword1"},
        )
        assert login_resp.status_code == 200
        redirect_resp = artisan_client.get("/dang-ky-xuong", follow_redirects=False)
        assert redirect_resp.status_code == 303
        assert redirect_resp.headers["location"] == "/nghe-nhan"


def test_public_media_upload_enforces_csrf_category_and_ip_rate_limit(
    make_client: ClientFactory,
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    png = _make_png_bytes()

    with make_client(auto_csrf=False, media_root=str(tmp_path), clock=clock) as raw_client:
        no_csrf = raw_client.post(
            "/api/workshop-applications/media",
            data={"category": "workshop"},
            files=[("files", ("ws.png", png, "image/png"))],
        )
        assert no_csrf.status_code == 403
        assert no_csrf.json()["error"]["code"] == "CSRF_INVALID"

    with make_client(
        media_root=str(tmp_path),
        clock=clock,
        public_media_rate_limit_max_uploads=2,
        public_media_rate_limit_window_seconds=900,
    ) as client:
        # Disallowed category (product) rejected on public endpoint
        bad_cat = client.post(
            "/api/workshop-applications/media",
            data={"category": "product"},
            files=[("files", ("p.png", png, "image/png"))],
        )
        assert bad_cat.status_code == 422
        assert bad_cat.json()["error"]["code"] == "MEDIA_INVALID_CATEGORY"

        # First 2 allowed uploads succeed, 3rd hits 429 RATE_LIMIT_EXCEEDED
        assert _upload_public_media(client, category="workshop")
        assert _upload_public_media(client, category="certificate")
        limited = client.post(
            "/api/workshop-applications/media",
            data={"category": "workshop"},
            files=[("files", ("ws3.png", png, "image/png"))],
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "retry-after" in limited.headers


def test_submit_workshop_application_creates_inactive_artisan_pending_app_and_blocks_login(
    make_client: ClientFactory,
    clean_auth_db: str,
    tmp_path: Path,
) -> None:
    with make_client(media_root=str(tmp_path)) as client:
        ws_media_id = _upload_public_media(client, category="workshop")
        cert_media_id = _upload_public_media(client, category="certificate")

        submit = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "Nguyễn Văn Hùng",
                "email": "Hung.Artisan@BatTrang.VN",
                "phone": "0912 345 678",
                "password": "ValidPassword1",
                "name_vi": "Xưởng Gốm Men Lam Cổ",
                "name_en": "Heritage Cobalt Workshop",
                "tagline_vi": "Bốn đời giữ lửa lò gốm",
                "address_vi": "Xóm 3, Xã Bát Tràng, Thành phố Hà Nội",
                "address_en": "Hamlet 3, Bát Tràng Commune, Hanoi",
                "history_vi": "Gia đình làm gốm thủ công tại Bát Tràng hơn 80 năm.",
                "opening_hours": "08:00 - 17:30",
                "is_open_now": True,
                "has_experience": True,
                "experience_desc_vi": "Trải nghiệm vuốt bàn xoay cùng nghệ nhân.",
                "latitude": 20.9772,
                "longitude": 105.9145,
                "workshop_media_ids": [ws_media_id],
                "certificate_media_ids": [cert_media_id],
            },
        )
        assert submit.status_code == 201
        assert "vcraft_session=" not in submit.headers.get("set-cookie", "").lower()

        data = submit.json()["data"]
        assert data["application_code"] == "APP-001"
        assert data["proposed_slug"] == "xuong-gom-men-lam-co"
        assert data["status"] == WorkshopApplicationStatus.PENDING.value

        # Pending account MUST be rejected on login (403 ACCOUNT_INACTIVE) & blocked from /nghe-nhan
        login_attempt = client.post(
            "/api/auth/login",
            json={"email": "hung.artisan@battrang.vn", "password": "ValidPassword1"},
        )
        assert login_attempt.status_code == 403
        assert login_attempt.json()["error"]["code"] == "ACCOUNT_INACTIVE"

        portal_resp = client.get("/nghe-nhan", follow_redirects=False)
        assert portal_resp.status_code == 303
        assert portal_resp.headers["location"].startswith("/dang-nhap")

        # Second application with identical workshop name gets unique slug & sequential code
        ws_media_2 = _upload_public_media(client, category="workshop")
        cert_media_2 = _upload_public_media(client, category="certificate")
        second = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "Trần Thị Mai",
                "email": "mai.artisan@battrang.vn",
                "phone": "0988 111 222",
                "password": "ValidPassword1",
                "name_vi": "Xưởng Gốm Men Lam Cổ",
                "address_vi": "Xóm 5, Xã Bát Tràng, Thành phố Hà Nội",
                "history_vi": "Xưởng gia truyền chuyên bình hút lộc men lam.",
                "opening_hours": "08:30 - 17:00",
                "workshop_media_ids": [ws_media_2],
                "certificate_media_ids": [cert_media_2],
            },
        )
        assert second.status_code == 201
        assert second.json()["data"]["application_code"] == "APP-002"
        assert second.json()["data"]["proposed_slug"] == "xuong-gom-men-lam-co-2"

    # Verify DB state: inactive Artisan user, owned media assets, and audit log entry
    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.email == "hung.artisan@battrang.vn"))
            assert user is not None
            assert user.role == UserRole.ARTISAN.value
            assert user.is_active is False

            app_row = db.scalar(
                select(WorkshopApplication).where(WorkshopApplication.user_id == user.id)
            )
            assert app_row is not None
            assert app_row.status == WorkshopApplicationStatus.PENDING.value

            owned_assets = list(
                db.scalars(select(MediaAsset).where(MediaAsset.owner_user_id == user.id)).all()
            )
            assert len(owned_assets) == 2

            audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.WORKSHOP_APPLICATION_SUBMITTED.value,
                    AuditLog.actor_user_id == user.id,
                )
            )
            assert audit is not None
            assert audit.target_id == "APP-001"
    finally:
        engine.dispose()


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_submit_workshop_application_rejects_duplicate_email_and_invalid_inputs(
    make_client: ClientFactory,
    tmp_path: Path,
    lang: str,
) -> None:
    with make_client(media_root=str(tmp_path)) as client:
        client.cookies.set(LANG_COOKIE_NAME, lang)

        # Missing required fields + out-of-range coordinates + fake media UUID -> 422
        invalid = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "A",
                "email": "not-an-email",
                "phone": "123",
                "password": "short",
                "name_vi": "",
                "address_vi": "abc",
                "history_vi": "too short",
                "opening_hours": "",
                "latitude": 120.0,
                "longitude": -200.0,
                "workshop_media_ids": [],
                "certificate_media_ids": [],
            },
        )
        assert invalid.status_code == 422
        field_errors = invalid.json()["meta"]["field_errors"]
        for expected_field in (
            "artisan_name",
            "email",
            "phone",
            "password",
            "name_vi",
            "address_vi",
            "history_vi",
            "opening_hours",
            "latitude",
            "longitude",
            "workshop_media_ids",
            "certificate_media_ids",
        ):
            assert expected_field in field_errors

        # Nonexistent / cross-category media_asset_id -> 422
        ws_id = _upload_public_media(client, category="workshop")
        bad_media = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "Nguyễn Văn Bình",
                "email": f"binh-{lang}@battrang.vn",
                "phone": "0912345678",
                "password": "ValidPassword1",
                "name_vi": "Xưởng Bình An",
                "address_vi": "Xóm 2, Xã Bát Tràng, Thành phố Hà Nội",
                "history_vi": "Xưởng gốm truyền thống lâu đời tại Bát Tràng.",
                "opening_hours": "08:00 - 17:00",
                "workshop_media_ids": [str(uuid.uuid4())],
                "certificate_media_ids": [
                    ws_id
                ],  # wrong category (workshop instead of certificate)
            },
        )
        assert bad_media.status_code == 422
        bad_media_errors = bad_media.json()["meta"]["field_errors"]
        assert "workshop_media_ids" in bad_media_errors
        assert "certificate_media_ids" in bad_media_errors

        # Duplicate email -> 409 EMAIL_ALREADY_REGISTERED
        cert_id = _upload_public_media(client, category="certificate")
        first = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "Nguyễn Văn Bình",
                "email": f"dup-{lang}@battrang.vn",
                "phone": "0912345678",
                "password": "ValidPassword1",
                "name_vi": "Xưởng Bình An",
                "address_vi": "Xóm 2, Xã Bát Tràng, Thành phố Hà Nội",
                "history_vi": "Xưởng gốm truyền thống lâu đời tại Bát Tràng.",
                "opening_hours": "08:00 - 17:00",
                "workshop_media_ids": [ws_id],
                "certificate_media_ids": [cert_id],
            },
        )
        assert first.status_code == 201

        ws_id_2 = _upload_public_media(client, category="workshop")
        cert_id_2 = _upload_public_media(client, category="certificate")
        dup = client.post(
            "/api/workshop-applications",
            json={
                "artisan_name": "Nguyễn Văn Bình 2",
                "email": f"DUP-{lang}@battrang.vn",
                "phone": "0912345679",
                "password": "ValidPassword1",
                "name_vi": "Xưởng Bình An 2",
                "address_vi": "Xóm 2, Xã Bát Tràng, Thành phố Hà Nội",
                "history_vi": "Xưởng gốm truyền thống lâu đời tại Bát Tràng.",
                "opening_hours": "08:00 - 17:00",
                "workshop_media_ids": [ws_id_2],
                "certificate_media_ids": [cert_id_2],
            },
        )
        assert dup.status_code == 409
        assert dup.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
        assert "email" in dup.json()["meta"]["field_errors"]
