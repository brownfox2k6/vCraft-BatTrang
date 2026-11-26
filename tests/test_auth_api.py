"""Integration tests for Auth JSON API (/api/auth/*) and storage security invariants."""

import hashlib
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import Argon2PasswordHasher
from app.i18n import LANG_COOKIE_NAME
from app.models.auth import User, UserRole, UserSession
from tests.conftest import ClientFactory, MutableClock


def _seed_user(
    database_url: str,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
    is_active: bool = True,
) -> None:
    hasher = Argon2PasswordHasher()
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.add(
                User(
                    email=email.lower(),
                    full_name=full_name,
                    password_hash=hasher.hash(password),
                    role=role.value,
                    is_active=is_active,
                )
            )
            db.commit()
    finally:
        engine.dispose()


def test_register_buyer_creates_argon2id_user_and_httponly_session(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    raw_password = "CeramicPass123"
    response = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Nguyễn Minh An",
            "email": "  Buyer.An@Example.COM ",
            "password": raw_password,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["error"] is None
    assert payload["meta"] == {}
    assert payload["data"]["redirect_to"] == "/"
    user_data = payload["data"]["user"]
    assert user_data["email"] == "buyer.an@example.com"
    assert user_data["full_name"] == "Nguyễn Minh An"
    assert user_data["role"] == "buyer"
    assert "id" in user_data
    assert raw_password not in response.text
    assert "password_hash" not in response.text

    set_cookie = response.headers.get("set-cookie", "")
    assert "vcraft_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    raw_cookie_token = auth_client.cookies.get("vcraft_session")
    assert raw_cookie_token is not None
    assert len(raw_cookie_token) >= 32

    me_response = auth_client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json() == {
        "data": {"user": user_data},
        "meta": {},
        "error": None,
    }

    # Storage security invariant (Seam 3): Argon2id password hash & SHA-256 session token hash
    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            stored_user = db.scalar(select(User).where(User.email == "buyer.an@example.com"))
            assert stored_user is not None
            assert stored_user.password_hash != raw_password
            assert stored_user.password_hash.startswith("$argon2id$")

            stored_session = db.scalar(
                select(UserSession).where(UserSession.user_id == stored_user.id)
            )
            assert stored_session is not None
            assert stored_session.token_hash != raw_cookie_token
            assert re.fullmatch(r"[0-9a-f]{64}", stored_session.token_hash)
            assert (
                stored_session.token_hash
                == hashlib.sha256(raw_cookie_token.encode("utf-8")).hexdigest()
            )
    finally:
        engine.dispose()


def test_me_requires_authenticated_session(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 401
    payload = response.json()
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHENTICATED"
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"] != ""


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("vi", "đã được đăng ký"),
        ("en", "already registered"),
    ],
)
def test_register_rejects_duplicate_email_case_insensitively_with_bilingual_error(
    auth_client: TestClient,
    lang: str,
    expected_fragment: str,
) -> None:
    first = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Minh An",
            "email": "buyer@example.com",
            "password": "CeramicPass123",
        },
    )
    assert first.status_code == 201

    auth_client.cookies.clear()
    auth_client.cookies.set(LANG_COOKIE_NAME, lang)
    duplicate = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Minh An 2",
            "email": "Buyer@Example.COM",
            "password": "CeramicPass123",
        },
    )

    assert duplicate.status_code == 409
    payload = duplicate.json()
    assert payload["data"] is None
    assert payload["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert expected_fragment in payload["error"]["message"].lower()
    assert "email" in payload["meta"]["field_errors"]


@pytest.mark.parametrize(
    "weak_password",
    [
        "short1",
        "onlyletters",
        "12345678",
        "a1" * 65,
    ],
)
@pytest.mark.parametrize("lang", ["vi", "en"])
def test_register_rejects_weak_passwords_with_bilingual_errors(
    auth_client: TestClient,
    weak_password: str,
    lang: str,
) -> None:
    auth_client.cookies.set(LANG_COOKIE_NAME, lang)
    response = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Minh An",
            "email": "weakpass@example.com",
            "password": weak_password,
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    field_errors = payload["meta"]["field_errors"]
    assert "password" in field_errors
    assert field_errors["password"] != ""
    if lang == "vi":
        assert "mật khẩu" in field_errors["password"].lower()
    else:
        assert "password" in field_errors["password"].lower()


def test_register_rejects_invalid_email_and_short_name(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "   A  ",
            "email": "not-an-email",
            "password": "CeramicPass123",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "full_name" in payload["meta"]["field_errors"]
    assert "email" in payload["meta"]["field_errors"]


@pytest.mark.parametrize(
    ("next_url", "expected_redirect"),
    [
        ("/kham-pha?page=2", "/kham-pha?page=2"),
        ("https://evil.example/steal", "/"),
        ("//evil.example/steal", "/"),
    ],
)
def test_register_sanitizes_next_redirect_target(
    auth_client: TestClient,
    next_url: str,
    expected_redirect: str,
) -> None:
    response = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Minh An",
            "email": "redirect-check@example.com",
            "password": "CeramicPass123",
            "next": next_url,
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["redirect_to"] == expected_redirect


@pytest.mark.parametrize(
    ("role", "expected_redirect"),
    [
        (UserRole.BUYER, "/"),
        (UserRole.ARTISAN, "/nghe-nhan"),
        (UserRole.ADMIN, "/quan-tri"),
    ],
)
def test_login_supports_all_roles_and_sets_httponly_cookie(
    auth_client: TestClient,
    clean_auth_db: str,
    role: UserRole,
    expected_redirect: str,
) -> None:
    email = f"{role.value}@battrang.vn"
    _seed_user(
        clean_auth_db,
        email=email,
        password="ValidPassword1",
        full_name=f"User {role.value}",
        role=role,
    )

    response = auth_client.post(
        "/api/auth/login",
        json={"email": f"  {email.upper()} ", "password": "ValidPassword1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["data"]["user"]["email"] == email
    assert payload["data"]["user"]["role"] == role.value
    assert payload["data"]["redirect_to"] == expected_redirect
    assert "ValidPassword1" not in response.text
    assert "password_hash" not in response.text

    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "vcraft_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" not in set_cookie

    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"]["role"] == role.value


def test_login_honors_safe_next_and_ignores_unsafe_next(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="artisan-next@battrang.vn",
        password="ValidPassword1",
        full_name="Nghệ nhân An",
        role=UserRole.ARTISAN,
    )

    safe_resp = auth_client.post(
        "/api/auth/login",
        json={
            "email": "artisan-next@battrang.vn",
            "password": "ValidPassword1",
            "next": "/nghe-nhan/san-pham",
        },
    )
    assert safe_resp.status_code == 200
    assert safe_resp.json()["data"]["redirect_to"] == "/nghe-nhan/san-pham"

    unsafe_resp = auth_client.post(
        "/api/auth/login",
        json={
            "email": "artisan-next@battrang.vn",
            "password": "ValidPassword1",
            "next": "https://evil.example/phish",
        },
    )
    assert unsafe_resp.status_code == 200
    assert unsafe_resp.json()["data"]["redirect_to"] == "/nghe-nhan"


@pytest.mark.parametrize("lang", ["vi", "en"])
@pytest.mark.parametrize(
    ("login_email", "login_password"),
    [
        ("buyer-fail@battrang.vn", "WrongPass1"),
        ("missing-user@battrang.vn", "ValidPassword1"),
    ],
)
def test_login_rejects_wrong_password_or_unknown_email_with_401(
    auth_client: TestClient,
    clean_auth_db: str,
    lang: str,
    login_email: str,
    login_password: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="buyer-fail@battrang.vn",
        password="ValidPassword1",
        full_name="Minh An",
        role=UserRole.BUYER,
    )
    auth_client.cookies.set(LANG_COOKIE_NAME, lang)

    response = auth_client.post(
        "/api/auth/login",
        json={"email": login_email, "password": login_password},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["data"] is None
    assert payload["error"]["code"] == "INVALID_CREDENTIALS"
    assert payload["error"]["message"] != ""
    assert "set-cookie" not in {k.lower() for k in response.headers}


def test_login_rejects_inactive_account_with_403(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="locked@battrang.vn",
        password="ValidPassword1",
        full_name="Xưởng bị khóa",
        role=UserRole.ARTISAN,
        is_active=False,
    )

    response = auth_client.post(
        "/api/auth/login",
        json={"email": "locked@battrang.vn", "password": "ValidPassword1"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "ACCOUNT_INACTIVE"
    assert "set-cookie" not in {k.lower() for k in response.headers}


def test_login_sets_secure_cookie_on_https_or_when_configured(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="https-buyer@battrang.vn",
        password="ValidPassword1",
        full_name="Minh An",
        role=UserRole.BUYER,
    )

    with make_client(base_url="https://testserver") as https_client:
        resp_https = https_client.post(
            "/api/auth/login",
            json={"email": "https-buyer@battrang.vn", "password": "ValidPassword1"},
        )
        assert resp_https.status_code == 200
        assert "secure" in resp_https.headers.get("set-cookie", "").lower()

    with make_client(session_cookie_secure=True) as forced_secure_client:
        resp_forced = forced_secure_client.post(
            "/api/auth/login",
            json={"email": "https-buyer@battrang.vn", "password": "ValidPassword1"},
        )
        assert resp_forced.status_code == 200
        assert "secure" in resp_forced.headers.get("set-cookie", "").lower()


def test_logout_deletes_server_session_and_invalidates_replayed_cookie(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    register_resp = auth_client.post(
        "/api/auth/register",
        json={
            "full_name": "Minh An",
            "email": "logout-buyer@battrang.vn",
            "password": "ValidPassword1",
        },
    )
    assert register_resp.status_code == 201
    old_token = auth_client.cookies.get("vcraft_session")
    assert old_token is not None

    logout_resp = auth_client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {
        "data": {"logged_out": True},
        "meta": {},
        "error": None,
    }
    set_cookie = logout_resp.headers.get("set-cookie", "").lower()
    assert "vcraft_session=" in set_cookie
    assert "max-age=0" in set_cookie

    # Replaying the old cookie must be rejected
    auth_client.cookies.set("vcraft_session", old_token)
    replayed = auth_client.get("/api/auth/me")
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "UNAUTHENTICATED"

    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            assert db.scalar(select(UserSession)) is None
    finally:
        engine.dispose()


def test_logout_without_cookie_is_idempotent(auth_client: TestClient) -> None:
    response = auth_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["data"] == {"logged_out": True}


def test_expired_session_is_rejected_and_deleted(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    clock = MutableClock()
    with make_client(clock=clock, session_ttl_seconds=60) as timed_client:
        reg = timed_client.post(
            "/api/auth/register",
            json={
                "full_name": "Timed Buyer",
                "email": "timed@battrang.vn",
                "password": "ValidPassword1",
            },
        )
        assert reg.status_code == 201
        assert timed_client.get("/api/auth/me").status_code == 200

        clock.advance(seconds=61)

        expired_me = timed_client.get("/api/auth/me")
        assert expired_me.status_code == 401
        assert expired_me.json()["error"]["code"] == "UNAUTHENTICATED"

    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            assert db.scalar(select(UserSession)) is None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("vi", "quá nhiều lần"),
        ("en", "too many"),
    ],
)
def test_login_rate_limits_after_consecutive_failures_and_recovers_after_window(
    make_client: ClientFactory,
    clean_auth_db: str,
    lang: str,
    expected_fragment: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="target@battrang.vn",
        password="ValidPassword1",
        full_name="Target User",
        role=UserRole.BUYER,
    )
    _seed_user(
        clean_auth_db,
        email="other@battrang.vn",
        password="ValidPassword1",
        full_name="Other User",
        role=UserRole.BUYER,
    )

    clock = MutableClock()
    with make_client(
        clock=clock,
        login_rate_limit_max_attempts=5,
        login_rate_limit_window_seconds=900,
    ) as limited_client:
        limited_client.cookies.set(LANG_COOKIE_NAME, lang)

        for _ in range(5):
            failed = limited_client.post(
                "/api/auth/login",
                json={"email": "target@battrang.vn", "password": "WrongPassword1"},
            )
            assert failed.status_code == 401

        # 6th attempt is blocked with 429 even with the correct password
        blocked = limited_client.post(
            "/api/auth/login",
            json={"email": "target@battrang.vn", "password": "ValidPassword1"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        payload = blocked.json()
        assert payload["data"] is None
        assert payload["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert expected_fragment in payload["error"]["message"].lower()

        # Another email from the same IP is unaffected
        other_resp = limited_client.post(
            "/api/auth/login",
            json={"email": "other@battrang.vn", "password": "ValidPassword1"},
        )
        assert other_resp.status_code == 200

        # Advancing clock past the sliding window lifts the block
        clock.advance(seconds=901)
        recovered = limited_client.post(
            "/api/auth/login",
            json={"email": "target@battrang.vn", "password": "ValidPassword1"},
        )
        assert recovered.status_code == 200


def test_successful_login_resets_failed_attempt_counter(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="reset@battrang.vn",
        password="ValidPassword1",
        full_name="Reset User",
        role=UserRole.BUYER,
    )

    clock = MutableClock()
    with make_client(
        clock=clock,
        login_rate_limit_max_attempts=5,
        login_rate_limit_window_seconds=900,
    ) as limited_client:
        for _ in range(3):
            assert (
                limited_client.post(
                    "/api/auth/login",
                    json={"email": "reset@battrang.vn", "password": "WrongPassword1"},
                ).status_code
                == 401
            )

        assert (
            limited_client.post(
                "/api/auth/login",
                json={"email": "reset@battrang.vn", "password": "ValidPassword1"},
            ).status_code
            == 200
        )

        # Counter was reset, so 3 more failures stay at 401 rather than 429
        for _ in range(3):
            assert (
                limited_client.post(
                    "/api/auth/login",
                    json={"email": "reset@battrang.vn", "password": "WrongPassword1"},
                ).status_code
                == 401
            )
