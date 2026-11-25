# vCraft Bát Tràng

Nền tảng triển lãm số, truy xuất nguồn gốc theo lô (QR), bản đồ số làng nghề và điều phối yêu cầu báo giá (RFQ) nhiều xưởng cho **Làng gốm Bát Tràng** (INT3306 – Phát triển ứng dụng web).

## Khởi chạy nhanh bằng Docker Compose

Yêu cầu: Docker & Docker Compose.

```bash
docker compose up --build
```

- Web server (FastAPI): `http://localhost:8000`
- Kiểm tra kết nối API & PostgreSQL 19: `GET http://localhost:8000/api/health`
- PostgreSQL 19 tự động khởi tạo sẵn 2 CSDL: `vcraft` (ứng dụng) và `vcraft_test` (kiểm thử).

## Migration & Kiểm thử

Chạy trong container `server`:

```bash
docker compose exec server alembic upgrade head
docker compose exec server pytest
```

Hoặc chạy local với virtualenv (`.venv`):

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install --upgrade pip && .venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
.venv/bin/alembic upgrade head
.venv/bin/ruff check app tests alembic && .venv/bin/ruff format --check app tests alembic
.venv/bin/mypy app tests alembic/env.py
.venv/bin/pytest
```
