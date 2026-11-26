"""Integration tests for SSR auth pages (/dang-nhap, /dang-ky, /dang-xuat) and header state."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import Argon2PasswordHasher
from app.i18n import LANG_COOKIE_NAME
from app.models.auth import User, UserRole, UserSession
from tests.conftest import ClientFactory


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


@pytest.mark.parametrize(
    ("path", "lang", "expected_title", "expected_heading"),
    [
        ("/dang-nhap", "vi", "Đăng nhập | vCraft Bát Tràng", "Đăng nhập vCraft"),
        ("/dang-nhap", "en", "Sign in | vCraft Bát Tràng", "Sign in to vCraft"),
        ("/dang-ky", "vi", "Đăng ký tài khoản | vCraft Bát Tràng", "Tạo tài khoản Buyer"),
        ("/dang-ky", "en", "Create Account | vCraft Bát Tràng", "Create a Buyer Account"),
    ],
)
def test_auth_pages_render_bilingually_with_validation_and_vary_cookie(
    auth_client: TestClient,
    path: str,
    lang: str,
    expected_title: str,
    expected_heading: str,
) -> None:
    auth_client.cookies.set(LANG_COOKIE_NAME, lang)
    response = auth_client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    vary_values = [v.strip().lower() for v in response.headers.get("vary", "").split(",") if v]
    assert "cookie" in vary_values

    html = response.text
    assert f"<title>{expected_title}</title>" in html
    assert expected_heading in html
    assert "/static/js/auth.js" in html
    assert 'type="email"' in html
    assert "required" in html
    assert "demo" not in html.lower()
    assert "inline-block whitespace-nowrap" in html
    if path == "/dang-ky":
        assert 'minlength="8"' in html
        assert 'name="confirm_password"' in html


def test_web_register_creates_buyer_sets_cookie_and_updates_header_and_logout(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    response = auth_client.post(
        "/dang-ky",
        data={
            "full_name": "Trần Bảo Ngọc",
            "email": "ngoc.buyer@battrang.vn",
            "password": "CeramicPass123",
            "confirm_password": "CeramicPass123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "vcraft_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    home = auth_client.get("/")
    assert home.status_code == 200
    assert "Trần Bảo Ngọc" in home.text
    assert 'action="/dang-xuat"' in home.text
    assert 'href="/dang-nhap"' not in home.text

    logout = auth_client.post("/dang-xuat", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/"
    assert "max-age=0" in logout.headers.get("set-cookie", "").lower()

    home_after = auth_client.get("/")
    assert home_after.status_code == 200
    assert 'href="/dang-nhap"' in home_after.text
    assert 'action="/dang-xuat"' not in home_after.text

    engine = create_engine(clean_auth_db)
    try:
        with Session(engine) as db:
            assert db.scalar(select(UserSession)) is None
    finally:
        engine.dispose()


def test_web_register_preserves_inputs_on_validation_or_duplicate_without_echoing_password(
    auth_client: TestClient,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="taken@battrang.vn",
        password="ValidPassword1",
        full_name="Existing Buyer",
        role=UserRole.BUYER,
    )

    mismatch = auth_client.post(
        "/dang-ky",
        data={
            "full_name": "Lê Minh",
            "email": "new@battrang.vn",
            "password": "SecretPass123",
            "confirm_password": "DifferentPass123",
        },
    )
    assert mismatch.status_code == 422
    assert "Lê Minh" in mismatch.text
    assert "new@battrang.vn" in mismatch.text
    assert "SecretPass123" not in mismatch.text
    assert "DifferentPass123" not in mismatch.text

    duplicate = auth_client.post(
        "/dang-ky",
        data={
            "full_name": "Lê Minh",
            "email": "taken@battrang.vn",
            "password": "SecretPass123",
            "confirm_password": "SecretPass123",
        },
    )
    assert duplicate.status_code == 409
    assert "taken@battrang.vn" in duplicate.text
    assert "SecretPass123" not in duplicate.text


@pytest.mark.parametrize(
    ("role", "expected_redirect"),
    [
        (UserRole.BUYER, "/"),
        (UserRole.ARTISAN, "/nghe-nhan"),
        (UserRole.ADMIN, "/quan-tri"),
    ],
)
def test_web_login_redirects_by_role_and_redirects_authenticated_auth_pages(
    auth_client: TestClient,
    clean_auth_db: str,
    role: UserRole,
    expected_redirect: str,
) -> None:
    email = f"web-{role.value}@battrang.vn"
    _seed_user(
        clean_auth_db,
        email=email,
        password="ValidPassword1",
        full_name=f"Web {role.value}",
        role=role,
    )

    resp = auth_client.post(
        "/dang-nhap",
        data={"email": email, "password": "ValidPassword1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == expected_redirect

    already_login = auth_client.get("/dang-nhap", follow_redirects=False)
    assert already_login.status_code == 303
    assert already_login.headers["location"] == expected_redirect

    already_register = auth_client.get("/dang-ky", follow_redirects=False)
    assert already_register.status_code == 303
    assert already_register.headers["location"] == expected_redirect


def test_web_login_renders_401_and_429_rate_limit_without_echoing_password(
    make_client: ClientFactory,
    clean_auth_db: str,
) -> None:
    _seed_user(
        clean_auth_db,
        email="web-rate@battrang.vn",
        password="ValidPassword1",
        full_name="Rate User",
        role=UserRole.BUYER,
    )

    with make_client(login_rate_limit_max_attempts=5, login_rate_limit_window_seconds=900) as c:
        c.cookies.set(LANG_COOKIE_NAME, "en")
        for _ in range(5):
            failed = c.post(
                "/dang-nhap",
                data={"email": "web-rate@battrang.vn", "password": "WrongPassword1"},
            )
            assert failed.status_code == 401
            assert "Incorrect email or password." in failed.text
            assert "WrongPassword1" not in failed.text

        blocked = c.post(
            "/dang-nhap",
            data={"email": "web-rate@battrang.vn", "password": "ValidPassword1"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert "Too many failed sign-in attempts" in blocked.text
        assert "ValidPassword1" not in blocked.text
