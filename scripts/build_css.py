#!/usr/bin/env python3
"""Compile Tailwind CSS v4 using the official Standalone CLI binary (no Node.js required)."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / ".tools"
INPUT_CSS = PROJECT_ROOT / "app" / "static" / "css" / "input.css"
OUTPUT_CSS = PROJECT_ROOT / "app" / "static" / "css" / "app.css"

DEFAULT_TAILWIND_VERSION = "v4.3.5"

ASSET_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "tailwindcss-macos-arm64",
    ("darwin", "x86_64"): "tailwindcss-macos-x64",
    ("linux", "x86_64"): "tailwindcss-linux-x64",
    ("linux", "aarch64"): "tailwindcss-linux-arm64",
    ("linux", "arm64"): "tailwindcss-linux-arm64",
    ("windows", "amd64"): "tailwindcss-windows-x64.exe",
    ("windows", "x86_64"): "tailwindcss-windows-x64.exe",
}


def resolve_asset_name() -> str:
    """Map the host OS and CPU architecture to the official Tailwind CLI asset name."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    asset = ASSET_MAP.get((system, machine))
    if asset is None:
        raise RuntimeError(f"Unsupported platform for Tailwind Standalone CLI: {system}/{machine}")
    return asset


def _is_tailwind_v4(binary: Path) -> bool:
    """Verify the given Tailwind CLI binary is v4.x (required for @theme syntax)."""
    probe = subprocess.run([str(binary), "--help"], capture_output=True, text=True, check=False)
    output = f"{probe.stdout}\n{probe.stderr}"
    return "tailwindcss v4." in output.lower()


def ensure_tailwind_binary() -> Path:
    """Return a Tailwind CSS v4 Standalone CLI binary, downloading a pinned release if needed."""
    on_path = shutil.which("tailwindcss")
    if on_path is not None:
        path_binary = Path(on_path)
        if _is_tailwind_v4(path_binary):
            return path_binary

    version = os.environ.get("TAILWIND_VERSION", DEFAULT_TAILWIND_VERSION)
    asset_name = resolve_asset_name()
    suffix = ".exe" if asset_name.endswith(".exe") else ""
    cached_binary = TOOLS_DIR / f"tailwindcss-{version}{suffix}"
    if cached_binary.exists():
        return cached_binary

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    download_url = (
        f"https://github.com/tailwindlabs/tailwindcss/releases/download/{version}/{asset_name}"
    )
    print(f"Downloading Tailwind CSS Standalone CLI {version} ({asset_name})...")
    tmp_path = cached_binary.with_suffix(".download")
    urllib.request.urlretrieve(download_url, tmp_path)
    tmp_path.replace(cached_binary)
    if not suffix:
        executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        cached_binary.chmod(cached_binary.stat().st_mode | executable_bits)
    return cached_binary


def build_css(*, watch: bool = False, minify: bool = True) -> None:
    """Compile input.css into app.css via the Tailwind Standalone CLI."""
    binary = ensure_tailwind_binary()
    command = [str(binary), "-i", str(INPUT_CSS), "-o", str(OUTPUT_CSS)]
    if watch:
        command.append("--watch")
    elif minify:
        command.append("--minify")

    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build vCraft Bat Trang Tailwind CSS bundle.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch templates and rebuild on change.",
    )
    parser.add_argument(
        "--no-minify",
        action="store_true",
        help="Skip minification in one-shot build.",
    )
    args = parser.parse_args(argv)
    build_css(watch=args.watch, minify=not args.no_minify)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
