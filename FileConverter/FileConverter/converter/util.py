"""Helpers for running external tools (pandoc, LibreOffice, ffmpeg)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from .engine import ConversionError

IS_WINDOWS = sys.platform.startswith("win")


def app_dir() -> Path:
    """Folder of the .exe when frozen with PyInstaller, else the project folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: str | Path | None = None, timeout: int = 900) -> str:
    """Run a command without flashing a console window on Windows."""
    kwargs = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=timeout, **kwargs)
    except FileNotFoundError:
        raise ConversionError(f"Program not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise ConversionError(f"{Path(cmd[0]).name} timed out")
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip().splitlines()
        raise ConversionError(f"{Path(cmd[0]).name}: " + (" ".join(msg[-3:]) or f"exit code {res.returncode}"))
    return res.stdout


def _bundled(*rel: str) -> str | None:
    """A tool shipped next to the app, e.g. tools/ffmpeg.exe."""
    for base in (app_dir(), app_dir() / "tools"):
        for r in rel:
            p = base / r
            if p.is_file():
                return str(p)
    return None


@lru_cache(None)
def pandoc_path() -> str | None:
    try:  # pypandoc_binary ships its own pandoc.exe
        import pypandoc
        p = pypandoc.get_pandoc_path()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    return _bundled("pandoc.exe", "pandoc") or shutil.which("pandoc")


@lru_cache(None)
def soffice_path() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    if IS_WINDOWS:
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                p = Path(base) / "LibreOffice" / "program" / "soffice.exe"
                if p.is_file():
                    return str(p)
    elif sys.platform == "darwin":
        p = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if p.is_file():
            return str(p)
    return None


@lru_cache(None)
def ffmpeg_path() -> str | None:
    p = _bundled("ffmpeg.exe", "ffmpeg") or shutil.which("ffmpeg")
    if p:
        return p
    try:  # pip install imageio-ffmpeg ships a static ffmpeg binary
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
