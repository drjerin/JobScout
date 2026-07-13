#!/usr/bin/env python3
"""Job Scout — local web app (Flask).

Runs on a laptop alongside the scheduler. Browse/filter/search matches, mark
jobs applied/hidden, trigger a fresh scan on demand, and edit the search
settings — all locally. The scheduled email keeps working independently.

    python app.py        # then open http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import yaml
from flask import Flask, jsonify, redirect, render_template, request, url_for

import logs
import store

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
log = logs.setup()

# Shared state for the background "Run now" job.
_run_state = {"running": False, "last": "idle", "log_tail": ""}
_run_lock = threading.Lock()

_ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌"}

# YAML files editable via the settings page (whitelist).
_EDITABLE_FILES = {
    "config": ROOT / "config.yaml",
    "matching": ROOT / "matching.yaml",
}


# ── config helpers ─────────────────────────────────────────────────────────
def _load_config() -> dict:
    path = ROOT / "config.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _enabled_countries(cfg: dict) -> list[tuple[str, dict]]:
    return [
        (name, ccfg)
        for name, ccfg in (cfg.get("countries") or {}).items()
        if (ccfg or {}).get("enabled")
    ]


def _section_label(name: str, ccfg: dict) -> str:
    emoji = (ccfg or {}).get("emoji") or ""
    return f"{emoji} {name}".strip()


# ── view helpers ───────────────────────────────────────────────────────────
def _decorate(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["notes_str"] = "  ".join(f"{_ICON.get(st, '•')} {label}"
                                   for st, label in (r.get("fit_notes") or []))
        p = r.get("match_percent") or 0
        r["color"] = "#15803d" if p >= 80 else "#b45309" if p >= 65 else "#6b7280"
        r["match_int"] = round(p)
    return rows


def _profile_labels(cfg: dict) -> dict:
    profile = cfg.get("profile") or {}
    return {
        "name": profile.get("name") or "Job Scout",
        "role": profile.get("role") or "",
    }


# ── routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    cfg = _load_config()
    status = request.args.get("status", "new")
    search = request.args.get("q") or None
    sort = request.args.get("sort", "match")

    sections = []
    for name, ccfg in _enabled_countries(cfg):
        rows = _decorate(store.query(name, status, search, sort))
        sections.append((_section_label(name, ccfg), rows))

    return render_template(
        "dashboard.html",
        sections=sections,
        counts=store.counts(),
        countries=[name for name, _ in _enabled_countries(cfg)],
        status=status, search=search or "", sort=sort, run=_run_state,
        profile=_profile_labels(cfg),
    )


@app.post("/api/status")
def api_status():
    data = request.get_json(force=True, silent=True) or {}
    job_id = str(data.get("id", ""))
    status = str(data.get("status", ""))
    if status not in store.VALID_STATUS:
        return jsonify(ok=False, error=f"invalid status '{status}'"), 400
    ok = store.set_status(job_id, status)
    return jsonify(ok=ok)


def _run_scout() -> None:
    with _run_lock:
        _run_state.update(running=True, last="running")
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "run.py"), "--no-email"],
            cwd=ROOT, capture_output=True, text=True, timeout=1800,
        )
        tail = (proc.stdout or "")[-4000:] + (proc.stderr or "")[-2000:]
        with _run_lock:
            _run_state.update(
                log_tail=tail,
                last="ok" if proc.returncode == 0 else f"error ({proc.returncode})",
            )
    except subprocess.TimeoutExpired:
        with _run_lock:
            _run_state.update(last="error: timed out after 30 min")
    except Exception as e:  # noqa: BLE001
        with _run_lock:
            _run_state.update(last=f"error: {e}")
    finally:
        with _run_lock:
            _run_state["running"] = False


@app.post("/api/run")
def api_run():
    with _run_lock:
        if _run_state["running"]:
            return jsonify(running=True, already=True)
        _run_state["running"] = True
        _run_state["last"] = "starting"
    threading.Thread(target=_run_scout, daemon=True).start()
    return jsonify(running=True)


@app.get("/api/run-status")
def api_run_status():
    with _run_lock:
        snapshot = dict(_run_state)
    return jsonify(snapshot)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    msg = ""
    if request.method == "POST":
        which = request.form.get("which", "")
        content = request.form.get("content", "")
        path = _EDITABLE_FILES.get(which)
        if not path:
            msg = "Unknown file."
        else:
            try:
                yaml.safe_load(content)          # validate before overwriting
                path.write_text(content, encoding="utf-8")
                msg = f"Saved {path.name} ✓  (applies on the next run)"
            except yaml.YAMLError as e:
                msg = f"NOT saved — invalid YAML: {e}"
        return redirect(url_for("settings", msg=msg))

    cfg = _load_config()
    files = {
        which: {
            "path": path,
            "content": path.read_text(encoding="utf-8") if path.exists() else "",
            "label": path.name,
        }
        for which, path in _EDITABLE_FILES.items()
    }
    return render_template(
        "settings.html",
        files=files,
        msg=request.args.get("msg", ""),
        profile=_profile_labels(cfg),
    )


def _bind() -> tuple[str, int]:
    """Read host/port from env first (JOBSCOUT_HOST/JOBSCOUT_PORT), then config."""
    cfg = _load_config().get("web") or {}
    host = os.getenv("JOBSCOUT_HOST", cfg.get("host") or "127.0.0.1")
    port = int(os.getenv("JOBSCOUT_PORT", cfg.get("port") or 8000))
    return host, port


if __name__ == "__main__":
    store.init_db()
    host, port = _bind()
    log.info("Job Scout UI running at http://%s:%d  (Ctrl+C to stop)", host, port)
    app.run(host=host, port=port, debug=False)
