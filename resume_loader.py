"""Load the resume from ``.txt``, ``.pdf``, or ``.docx``.

The first supported file found in the project root wins. PDF/DOCX extraction
uses optional dependencies (``pypdf`` and ``python-docx``) — if they aren't
installed, the loader falls back to plain text and prints a helpful message.
"""
from __future__ import annotations

from pathlib import Path

import logs

_log = logs.get("scout.resume")

_PLACEHOLDER_MARKER = "PASTE THE RESUME HERE"
_MIN_LEN = 60
_CANDIDATES = ("resume.txt", "resume.pdf", "resume.docx")


def load(root: Path) -> str:
    """Return the resume text, or the placeholder text if none is found."""
    for name in _CANDIDATES:
        path = root / name
        if not path.exists():
            continue
        try:
            text = _read(path)
        except Exception as e:  # noqa: BLE001 - resume load is best-effort
            _log.warning("could not read %s: %s", name, e)
            continue
        text = (text or "").strip()
        if _looks_like_placeholder(text):
            _log.warning(
                "%s still looks like the placeholder — matching quality will "
                "be poor until you paste (or drop in) the real resume.",
                name,
            )
        return text
    _log.warning("no resume file found (looked for %s)", ", ".join(_CANDIDATES))
    return ""


def _read(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            _log.warning("pypdf not installed; run `pip install pypdf` to read PDF resumes")
            return ""
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            _log.warning("python-docx not installed; run `pip install python-docx` to read DOCX resumes")
            return ""
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    return ""


def _looks_like_placeholder(text: str) -> bool:
    return _PLACEHOLDER_MARKER in text or len(text) < _MIN_LEN
