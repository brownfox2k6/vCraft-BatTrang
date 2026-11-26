# vCraft Bát Tràng — Engineering Rules

Shared conventions for contributors and coding agents. For local setup, Docker Compose services, and tool configuration, read `README.md`, `docker-compose.yml`, and `pyproject.toml`.

## Architecture & Routing

- **Stack**: FastAPI (`create_app` factory in `app/main.py`) + Jinja2 SSR + SQLAlchemy 2 ORM + Alembic + PostgreSQL 19 + Tailwind CSS v4 Standalone CLI + Vanilla JS ES modules. Keep the repository free of Node.js (`package.json`, `node_modules`) and Play CDN scripts.
- **API URLs**: Expose JSON endpoints under `/api/...` directly without version segments (`/v1`, `/v2`).
- **SSR Page URLs**: Keep canonical Vietnamese semantic paths regardless of active language (`/`, `/kham-pha`, `/san-pham/{slug}`, `/xuong`, `/xuong/{slug}`, `/ban-do`, `/lo-gom/{batch_code}`, `/tin-lang-nghe`, `/yeu-cau-bao-gia/{rfq_code}`, `/dang-nhap`, `/dang-ky`, `/dang-xuat`, `/nghe-nhan/...`, `/quan-tri/...`). Persist language via `POST /lang` (`vcraft_lang` cookie) and preserve `Vary: Cookie` on HTML responses.

## Templates, Design System & Dark Mode

- **Layouts**: Extend `app/templates/base.html` for public exhibition pages and `app/templates/layouts/workspace.html` for Artisan (`/nghe-nhan/...`) and Management Board (`/quan-tri/...`) portals.
- **Page `<title>`**: Render `vCraft Bát Tràng` alone on `/` and `{page_title} | vCraft Bát Tràng` on sub-pages and workspaces.
- **Semantic tokens**: Style surfaces, borders, text, backdrops, and actions exclusively with the `@theme static` semantic tokens defined in `app/static/css/input.css` (`cream`, `cream-deep`, `surface`, `backdrop`, `cobalt`, `cobalt-soft`, `cobalt-action`, `cobalt-action-hover`, `on-cobalt`, `terracotta`, `terracotta-soft`, `ink`, `ink-muted`, `clay-border`). Updating `:root` / `:root.dark` tokens keeps the 260ms `@property <color>` theme transition synchronized across Light and Dark modes without child transition conflicts.
- **CSS builds**: Edit `app/static/css/input.css`, compile via `.venv/bin/python scripts/build_css.py`, and commit the resulting `app/static/css/app.css`.
- **Accessibility & Wrapping**: Keep toggle controls (`theme`, `lang`) with a stable `aria-label` describing the control and a changing `aria-pressed` state (`true`/`false`), use `whitespace-nowrap shrink-0` on horizontal nav controls, apply `inline-block whitespace-nowrap` (without inner leading/trailing spaces) on inline CTA links after prompt sentences so multi-word links move as one unit, and add `text-pretty` on non-`<p>` alert/message containers (such as `.alert-error`).

## i18n, Typography & Domain Copy

- **Locale catalogs**: Keep `app/i18n/locales/vi.json` and `app/i18n/locales/en.json` key-identical and clean plain UTF-8 text free of `\u00a0` or `\u2011` escapes. Register indivisible proper nouns and domain compounds once (matching is case-insensitive) in `app/i18n/catalog.py` (`_NON_BREAKING_PHRASES`), where phrase binding, intra-word `\u2011`, quantity-unit binding, glue-word binding, and 4+-token orphan protection run once inside `@lru_cache`.
- **Intentional breaks**: Reserve `\n` in locale strings for deliberate display breaks rendered with `whitespace-pre-line` (such as `home.hero_title`). Keep `<title>` keys (`_PLAIN_TEXT_KEYS`, `*.page_title`), `*_aria` keys, and JSON API error strings (`auth.errors.*`) free of NBSP.
- **Dynamic content & formatting**: Resolve bilingual DB fields with `localize()` (`app/i18n/fallback.py`, falling back to `vi`) and format currency/dates with `format_currency`, `format_date`, and `format_datetime` (`app/i18n/formatting.py`, timezone `Asia/Ho_Chi_Minh`).
- **Administrative accuracy**: Always write **Xã Bát Tràng, Thành phố Hà Nội** (or **Bát Tràng Commune, Hanoi** in English) — replace any legacy references such as *Huyện Gia Lâm* or *Thôn Bát Tràng*.

## Python, Database & Verification

- **Strict typing & lint**: Every Python file in `app/`, `tests/`, `scripts/`, and `alembic/env.py` must pass `mypy` (`strict = true`), `ruff check`, and `ruff format --check` cleanly.
- **PostgreSQL 19**: Keep Docker Compose `db` volume mounted at `/var/lib/postgresql` (required by Postgres 18+/19) and test isolation wired to `vcraft_test`.
- **Before every commit**: Pass `.venv/bin/pre-commit run --all-files`, `.venv/bin/pytest`, and `docker compose exec -T server pytest`.
- **UI & browser verification**: For UI, form, or copy changes, verify live rendered pages in a real browser across `1440px`, `1280px`, `375px`, and `320px`, both `VI | EN`, and Light/Dark modes for zero horizontal overflow, semantic line breaks without orphaned words/links, and interactive client-side flows; clean up any temporary test rows from the dev `vcraft` database afterward.
- **Test credentials**: Use obvious placeholder strings containing `Password` or `Pass` (e.g. `ValidPassword1`, `WrongPassword1`) instead of `Secret` in test fixtures so GitGuardian PR checks pass without false positives.

## Git Workflow

- **Feature branches & PRs**: Create a dedicated branch from `main` for every issue or task (e.g., `feat/issue-4-auth`, `fix/lang-switcher`), commit only on that branch, wait for all PR checks (CI and GitGuardian) to pass before merging, and preserve individual logical commits with `--merge` unless asked to squash. Never commit or push directly to `main`.
- **Issue-scoped commits**: Keep each commit focused on a single GitHub issue or logical unit, and push only when explicitly requested by the user.
