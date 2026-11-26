"""Integration tests for CSRF protection, 3-role RBAC + ownership guards, and audit logs."""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import Argon2PasswordHasher
from app.models.audit import AuditLog
from app.models.auth import User, UserRole, UserSession
from app.repositories.audit_repository import AuditRepository
from app.routers.guards import ApiGuardError, WebForbiddenError, require_owner_or_admin
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import AuthenticatedUser
from tests.conftest import ClientFactory


def _seed_user(
    database_url: str,
    *,
    email: str,
    full_name: str,
    password: str = "ValidPassword1",
    role: UserRole = UserRole.BUYER,
    is_active: bool = True,
) -> User:
    hasher = Argon2PasswordHasher()
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hasher.hash(password),
                role=role.value,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
    finally:
        engine.dispose()


def _extract_meta_csrf(html: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login_with_csrf(
    client: TestClient,
    *,
    email: str,
    password: str = "ValidPassword1",
) -> str:
    page = client.get("/dang-nhap")
    assert page.status_code == 200
    pre_csrf = _extract_meta_csrf(page.text)
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": pre_csrf},
    )
    assert resp.status_code == 200
    session_csrf = client.cookies.get("vcraft_csrf")
    assert session_csrf is not None and session_csrf != pre_csrf
    return session_csrf


def test_csrf_rejects_missing_and_invalid_tokens_across_mutating_methods(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    _seed_user(clean_auth_db, email="buyer@example.com", full_name="Buyer One")

    with make_client(auto_csrf=False) as raw_client:
        # Anonymous POST without CSRF cookie/header -> 403 JSON on /api/*
        missing_api = raw_client.post(
            "/api/auth/login",
            json={"email": "buyer@example.com", "password": "ValidPassword1"},
        )
        assert missing_api.status_code == 403
        assert missing_api.json()["error"]["code"] == "CSRF_INVALID"

        # Anonymous POST to SSR route without CSRF -> 403 HTML
        missing_ssr = raw_client.post("/lang", data={"lang": "en", "next": "/"})
        assert missing_ssr.status_code == 403
        assert "text/html" in missing_ssr.headers["content-type"]

        # Obtain anonymous CSRF token from HTML meta tag
        home = raw_client.get("/")
        assert home.status_code == 200
        anon_csrf = _extract_meta_csrf(home.text)

        # Wrong header token -> 403
        wrong_api = raw_client.post(
            "/api/auth/login",
            json={"email": "buyer@example.com", "password": "ValidPassword1"},
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert wrong_api.status_code == 403
        assert wrong_api.json()["error"]["code"] == "CSRF_INVALID"

        # Valid hidden form field _csrf_token works for SSR forms without JS
        ok_lang = raw_client.post(
            "/lang",
            data={"lang": "en", "next": "/", "_csrf_token": anon_csrf},
            follow_redirects=False,
        )
        assert ok_lang.status_code == 303

        # Login binds a fresh session-scoped CSRF token stored in user_sessions
        session_csrf = _login_with_csrf(raw_client, email="buyer@example.com")

        engine = create_engine(clean_auth_db)
        try:
            with Session(engine) as db:
                stored_session = db.scalar(select(UserSession))
                assert stored_session is not None
                assert stored_session.csrf_token == session_csrf
        finally:
            engine.dispose()

        # Stale pre-login token and missing header on PUT/PATCH/DELETE are rejected with 403
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            stale_resp = raw_client.request(
                method,
                "/api/auth/logout",
                headers={"X-CSRF-Token": anon_csrf},
            )
            assert stale_resp.status_code == 403
            assert stale_resp.json()["error"]["code"] == "CSRF_INVALID"

        # Valid session CSRF token succeeds
        ok_logout = raw_client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": session_csrf},
        )
        assert ok_logout.status_code == 200
        assert ok_logout.json()["data"]["logged_out"] is True


def test_frontend_api_js_module_is_served_and_wired_into_auth_js(client: TestClient) -> None:
    api_js = client.get("/static/js/api.js")
    assert api_js.status_code == 200
    assert "X-CSRF-Token" in api_js.text
    assert "apiFetch" in api_js.text

    auth_js = client.get("/static/js/auth.js")
    assert auth_js.status_code == 200
    assert "./api.js" in auth_js.text

    layout_js = client.get("/static/js/layout.js")
    assert layout_js.status_code == 200
    assert "./api.js" in layout_js.text


def test_rbac_blocks_unauthenticated_and_cross_role_access_across_three_roles(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    _seed_user(clean_auth_db, email="buyer@example.com", full_name="Buyer", role=UserRole.BUYER)
    _seed_user(
        clean_auth_db,
        email="artisan@example.com",
        full_name="Artisan",
        role=UserRole.ARTISAN,
    )
    _seed_user(clean_auth_db, email="admin@example.com", full_name="Admin", role=UserRole.ADMIN)

    # Unauthenticated visitor: 303 redirect on SSR portals, 401 JSON on Admin API
    with make_client(auto_csrf=False) as anon:
        r_artisan = anon.get("/nghe-nhan?tab=orders&page=2", follow_redirects=False)
        assert r_artisan.status_code == 303
        assert (
            r_artisan.headers["location"] == "/dang-nhap?next=/nghe-nhan%3Ftab%3Dorders%26page%3D2"
        )

        r_admin = anon.get("/quan-tri", follow_redirects=False)
        assert r_admin.status_code == 303
        assert r_admin.headers["location"] == "/dang-nhap?next=/quan-tri"

        r_api = anon.get("/api/admin/audit-logs")
        assert r_api.status_code == 401
        assert r_api.json()["error"]["code"] == "UNAUTHENTICATED"

    # Buyer: blocked (403) from Artisan portal, Admin portal, and Admin API
    with make_client(auto_csrf=False) as buyer_client:
        _login_with_csrf(buyer_client, email="buyer@example.com")
        assert buyer_client.get("/nghe-nhan").status_code == 403
        assert buyer_client.get("/quan-tri").status_code == 403
        api_resp = buyer_client.get("/api/admin/audit-logs")
        assert api_resp.status_code == 403
        assert api_resp.json()["error"]["code"] == "FORBIDDEN"

    # Artisan: allowed on /nghe-nhan, blocked (403) on /quan-tri and Admin API
    with make_client(auto_csrf=False) as artisan_client:
        _login_with_csrf(artisan_client, email="artisan@example.com")
        assert artisan_client.get("/nghe-nhan").status_code == 200
        assert artisan_client.get("/quan-tri").status_code == 403
        assert artisan_client.get("/api/admin/audit-logs").status_code == 403

    # Admin: allowed on /quan-tri and Admin API, blocked (403) on Artisan portal (strict isolation)
    with make_client(auto_csrf=False) as admin_client:
        _login_with_csrf(admin_client, email="admin@example.com")
        assert admin_client.get("/quan-tri").status_code == 200
        assert admin_client.get("/nghe-nhan").status_code == 403
        logs_resp = admin_client.get("/api/admin/audit-logs")
        assert logs_resp.status_code == 200
        assert logs_resp.json()["error"] is None
        assert isinstance(logs_resp.json()["data"], list)


def test_ownership_guard_allows_owner_and_admin_and_blocks_others() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    owner = AuthenticatedUser(
        id=owner_id, email="owner@example.com", full_name="Owner", role=UserRole.ARTISAN
    )
    other = AuthenticatedUser(
        id=other_id, email="other@example.com", full_name="Other", role=UserRole.ARTISAN
    )
    admin = AuthenticatedUser(
        id=admin_id, email="admin@example.com", full_name="Admin", role=UserRole.ADMIN
    )

    require_owner_or_admin(owner_id, owner, api=True)
    require_owner_or_admin(owner_id, admin, api=True)

    with pytest.raises(ApiGuardError) as api_exc:
        require_owner_or_admin(owner_id, other, api=True)
    assert api_exc.value.status_code == 403
    assert api_exc.value.code == "FORBIDDEN"

    with pytest.raises(WebForbiddenError):
        require_owner_or_admin(owner_id, other, api=False)


def test_audit_logs_record_auth_lifecycle_and_sensitive_admin_actions(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    admin = _seed_user(
        clean_auth_db,
        email="admin@example.com",
        full_name="Board Admin",
        role=UserRole.ADMIN,
    )

    with make_client(auto_csrf=False) as raw_client:
        # 1. Failed login (unknown email)
        login_page = raw_client.get("/dang-nhap")
        anon_csrf = _extract_meta_csrf(login_page.text)
        bad_login = raw_client.post(
            "/api/auth/login",
            json={"email": "ghost@example.com", "password": "WrongPassword1"},
            headers={"X-CSRF-Token": anon_csrf},
        )
        assert bad_login.status_code == 401

        # 2. Failed login (wrong password for existing user)
        wrong_pw = raw_client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "WrongPassword1"},
            headers={"X-CSRF-Token": anon_csrf},
        )
        assert wrong_pw.status_code == 401

        # 3. Successful login + logout
        session_csrf = _login_with_csrf(raw_client, email="admin@example.com")
        logout_resp = raw_client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": session_csrf},
        )
        assert logout_resp.status_code == 200

        # 4. Record a sensitive admin action via AuditService
        engine = create_engine(clean_auth_db)
        try:
            with Session(engine) as db:
                audit_service = AuditService(repository=AuditRepository(db))
                audit_service.record(
                    action="admin.workshop_verified",
                    actor_user_id=admin.id,
                    actor_email=admin.email,
                    target_type="workshop",
                    target_id="ws-001",
                    ip_address="127.0.0.1",
                    details={"status": "verified"},
                    commit=True,
                )
        finally:
            engine.dispose()

        # 5. Re-login as Admin and query GET /api/admin/audit-logs
        _login_with_csrf(raw_client, email="admin@example.com")
        logs_resp = raw_client.get("/api/admin/audit-logs?limit=20")
        assert logs_resp.status_code == 200
        payload = logs_resp.json()
        actions = [entry["action"] for entry in payload["data"]]

        assert AuditAction.AUTH_LOGIN_FAILED.value in actions
        assert AuditAction.AUTH_LOGIN_SUCCESS.value in actions
        assert AuditAction.AUTH_LOGOUT.value in actions
        assert "admin.workshop_verified" in actions

        # Verify required fields are populated on persisted audit rows
        engine = create_engine(clean_auth_db)
        try:
            with Session(engine) as db:
                rows = list(db.scalars(select(AuditLog)).all())
                assert len(rows) >= 5
                by_action = {row.action: row for row in rows}
                login_row = by_action[AuditAction.AUTH_LOGIN_SUCCESS.value]
                assert login_row.actor_user_id == admin.id
                assert login_row.actor_email == admin.email
                assert login_row.target_type == "session"
                assert login_row.target_id is not None

                admin_row = by_action["admin.workshop_verified"]
                assert admin_row.actor_user_id == admin.id
                assert admin_row.target_type == "workshop"
                assert admin_row.target_id == "ws-001"

                for row in rows:
                    assert row.created_at is not None
                    assert row.action
                    assert row.ip_address is not None
        finally:
            engine.dispose()
