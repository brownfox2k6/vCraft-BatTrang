# vCraft Bát Tràng

Nền tảng triển lãm số, truy xuất nguồn gốc theo lô (QR), bản đồ số làng nghề và điều phối yêu cầu báo giá (RFQ) nhiều xưởng cho **Làng gốm Bát Tràng** (INT3306 – Phát triển ứng dụng web).

## 1. Khởi chạy nhanh bằng Docker Compose

Yêu cầu: Docker & Docker Compose.

```bash
docker compose up --build
```

- Web server (FastAPI): `http://localhost:8000`
- Kiểm tra kết nối API & PostgreSQL 19: `GET http://localhost:8000/api/health`
- PostgreSQL 19 tự động khởi tạo sẵn 2 CSDL: `vcraft` (ứng dụng) và `vcraft_test` (kiểm thử).

## 2. Thiết lập môi trường phát triển local (chạy 1 lần sau khi clone)

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install --upgrade pip && .venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
```

Sau bước này, mỗi lần `git commit` hệ thống sẽ tự động chạy `ruff check --fix`, `ruff format`, kiểm tra YAML/TOML và `mypy --strict`.

## 3. Biên dịch CSS (Tailwind CSS v4 Standalone CLI)

Không cần Node.js hay `node_modules`. Khi sửa template hoặc `app/static/css/input.css`, chạy:

```bash
.venv/bin/python scripts/build_css.py          # build tối ưu (minify) ra app/static/css/app.css
.venv/bin/python scripts/build_css.py --watch  # tự build lại khi đang phát triển
```

## 4. Migration & Kiểm thử

Chạy trong container `server`:

```bash
docker compose exec server alembic upgrade head
docker compose exec server pytest
```

Hoặc chạy bằng `.venv` ở máy local:

```bash
.venv/bin/alembic upgrade head
.venv/bin/ruff check app tests alembic scripts && .venv/bin/ruff format --check app tests alembic scripts
.venv/bin/mypy
.venv/bin/pytest
```
