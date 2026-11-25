"""Jinja2 templating and static asset paths shared by presentation routers."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"


def create_templates() -> Jinja2Templates:
    """Create a Jinja2Templates engine pointing at the app templates directory."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))
