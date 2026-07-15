#!/usr/bin/env python3
"""Job Scout — local web app (Flask).

Runs on a laptop alongside (or instead of) an OS scheduler. Browse/filter/search
matches, mark jobs applied/hidden, trigger a fresh scan on demand, and edit the
search settings — all locally.

Optional flags:

    python app.py                    # Flask only, plus in-process scheduler
    python app.py --tray             # add a system-tray icon
    python app.py --no-scheduler     # disable the in-process 6-hourly job
"""
from __future__ import annotations

import argparse
import os
import threading
import traceback
from pathlib import Path

import yaml
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import locations
import logs
import resume_loader
import store

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB cap on resume uploads
log = logs.setup()

_run_state = {"running": False, "last": "idle", "log_tail": ""}
_run_lock = threading.Lock()
_scheduler_lock = threading.Lock()
_scheduler_ref: dict = {"sched": None, "paused": False}

_ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌"}
_ALLOWED_RESUME_EXTS = {".txt", ".pdf", ".docx"}

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


def _save_config(cfg: dict) -> None:
    path = ROOT / "config.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def _load_matching() -> dict:
    path = ROOT / "matching.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_matching(cfg: dict) -> None:
    path = ROOT / "matching.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def _enabled_countries(cfg: dict) -> list[tuple[str, dict]]:
    return [
        (name, ccfg)
        for name, ccfg in (cfg.get("countries") or {}).items()
        if (ccfg or {}).get("enabled")
    ]


def _section_label(name: str, ccfg: dict) -> str:
    emoji = (ccfg or {}).get("emoji") or ""
    return f"{emoji} {name}".strip()


def _profile_labels(cfg: dict) -> dict:
    profile = cfg.get("profile") or {}
    return {
        "name": profile.get("name") or "Job Scout",
        "role": profile.get("role") or "",
    }


# ── first-run detection ────────────────────────────────────────────────────
_ENV_PLACEHOLDERS = ("youraddress@gmail.com", "your16charapppassword")
_RESUME_PLACEHOLDER = "PASTE THE RESUME HERE"


def _needs_setup() -> bool:
    """Return True when any critical piece of setup is still a placeholder."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return True
    env_text = env_file.read_text(encoding="utf-8", errors="ignore")
    if any(p in env_text for p in _ENV_PLACEHOLDERS):
        return True

    resume_text = resume_loader.load(ROOT)
    if len(resume_text) < 60 or _RESUME_PLACEHOLDER in resume_text:
        return True

    cfg = _load_config()
    if not _enabled_countries(cfg):
        return True

    if not (cfg.get("profile") or {}).get("role") or \
       (cfg.get("profile") or {}).get("role") == "Your Target Role":
        return True

    return False


def _env_kv() -> dict[str, str]:
    """Parse `.env` into a dict (very small, forgiving parser)."""
    path = ROOT / ".env"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _write_env(kv: dict[str, str]) -> None:
    """Write `.env` from a dict, preserving example comments as a header."""
    path = ROOT / ".env"
    header = [
        "# Written by the Job Scout setup wizard. Edit freely.",
        "# NEVER commit this file.",
        "",
    ]
    body = [f"{k}={v}" for k, v in kv.items() if k]
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")


# ── view helpers ───────────────────────────────────────────────────────────
def _decorate(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["notes_str"] = "  ".join(f"{_ICON.get(st, '•')} {label}"
                                   for st, label in (r.get("fit_notes") or []))
        p = r.get("match_percent") or 0
        r["color"] = "#15803d" if p >= 80 else "#b45309" if p >= 65 else "#6b7280"
        r["match_int"] = round(p)
    return rows


# ── routes: dashboard, jobs, settings ──────────────────────────────────────
@app.route("/")
def dashboard():
    if _needs_setup():
        return redirect(url_for("setup"))

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


def _run_scout_inprocess(no_email: bool = True) -> None:
    """Call ``run.run_once`` inside this process; capture a log tail for the UI."""
    from io import StringIO
    import logging

    with _run_lock:
        _run_state.update(running=True, last="running")

    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(name)s: %(message)s",
                                           datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        import run as run_module
        summary = run_module.run_once(dry_run=False, no_email=no_email)
        last = f"ok ({summary.get('scored', 0)} scored, {summary.get('total_top', 0)} top)"
    except Exception as e:  # noqa: BLE001
        last = f"error: {e}"
        buf.write("\n" + traceback.format_exc())
        log.exception("run_once failed")
    finally:
        root.removeHandler(handler)
        tail = buf.getvalue()[-6000:]
        with _run_lock:
            _run_state.update(running=False, last=last, log_tail=tail)


@app.post("/api/run")
def api_run():
    with _run_lock:
        if _run_state["running"]:
            return jsonify(running=True, already=True)
        _run_state["running"] = True
        _run_state["last"] = "starting"
    threading.Thread(target=_run_scout_inprocess, kwargs={"no_email": True},
                     daemon=True).start()
    return jsonify(running=True)


@app.get("/api/run-status")
def api_run_status():
    with _run_lock:
        snapshot = dict(_run_state)
    return jsonify(snapshot)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if _needs_setup():
        return redirect(url_for("setup"))
    if request.method == "POST":
        which = request.form.get("which", "")
        content = request.form.get("content", "")
        path = _EDITABLE_FILES.get(which)
        if not path:
            msg = "Unknown file."
        else:
            try:
                yaml.safe_load(content)
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


# ── routes: setup wizard ───────────────────────────────────────────────────
_WIZARD_STEPS = ["profile", "locations", "resume", "credentials", "done"]


def _wizard_next(step: str) -> str:
    idx = _WIZARD_STEPS.index(step) if step in _WIZARD_STEPS else 0
    return _WIZARD_STEPS[min(idx + 1, len(_WIZARD_STEPS) - 1)]


def _resume_state() -> dict:
    """Return a summary of the current resume file for the wizard UI."""
    for name in ("resume.txt", "resume.pdf", "resume.docx"):
        p = ROOT / name
        if p.exists():
            text = resume_loader.load(ROOT)
            placeholder = _RESUME_PLACEHOLDER in text or len(text) < 60
            return {
                "present": not placeholder,
                "filename": name,
                "chars": len(text),
            }
    return {"present": False, "filename": None, "chars": 0}


@app.route("/setup", methods=["GET"])
def setup():
    step = request.args.get("step", "profile")
    if step not in _WIZARD_STEPS:
        step = "profile"

    cfg = _load_config()
    profile = cfg.get("profile") or {}
    countries_cfg = cfg.get("countries") or {}
    current_countries = {
        name: [loc.split(",")[0].strip() for loc in (ccfg or {}).get("locations", [])]
        for name, ccfg in countries_cfg.items()
    }

    env = _env_kv()
    prof_input = {"name": profile.get("name", ""), "role": profile.get("role", "")}
    return render_template(
        "setup.html",
        step=step,
        steps=_WIZARD_STEPS,
        profile=prof_input,
        countries_catalog=locations.COUNTRIES,
        countries_current=current_countries,
        resume=_resume_state(),
        env=env,
        msg=request.args.get("msg", ""),
    )


@app.post("/api/setup/profile")
def api_setup_profile():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip() or "Job Scout"
    role = (data.get("role") or "").strip()
    if not role:
        return jsonify(ok=False, error="Role is required"), 400

    cfg = _load_config()
    cfg.setdefault("profile", {})
    cfg["profile"]["name"] = name
    cfg["profile"]["role"] = role

    existing = cfg.get("search_terms") or []
    if not existing or existing == ["Your Target Role"] or role not in existing:
        cfg["search_terms"] = [role] + [t for t in existing if t and t != "Your Target Role"]

    _save_config(cfg)

    req = _load_matching()
    titles = req.get("target_titles") or []
    if not titles and role:
        req["target_titles"] = [role]
        _save_matching(req)

    return jsonify(ok=True, next=_wizard_next("profile"))


@app.post("/api/setup/locations")
def api_setup_locations():
    """Body: {"selections": {"India": ["Bengaluru", "Mumbai"], ...}}"""
    data = request.get_json(force=True, silent=True) or {}
    selections = data.get("selections") or {}
    if not any(cities for cities in selections.values()):
        return jsonify(ok=False, error="Pick at least one city"), 400

    cfg = _load_config()
    cfg["countries"] = {
        name: locations.build_country_block(name, list(cities))
        for name, cities in selections.items()
        if cities
    }
    _save_config(cfg)

    req = _load_matching()
    req["allowed_countries"] = list(cfg["countries"].keys())
    _save_matching(req)

    return jsonify(ok=True, next=_wizard_next("locations"))


@app.post("/api/setup/resume")
def api_setup_resume():
    f = request.files.get("resume")
    if not f or not f.filename:
        return jsonify(ok=False, error="No file was uploaded"), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in _ALLOWED_RESUME_EXTS:
        return jsonify(ok=False,
                       error=f"Unsupported file type '{ext}' — use .txt, .pdf or .docx"), 400

    for other in _ALLOWED_RESUME_EXTS:
        candidate = ROOT / f"resume{other}"
        if candidate.exists() and other != ext:
            candidate.unlink(missing_ok=True)

    dest = ROOT / f"resume{ext}"
    f.save(dest)

    def _reject(msg: str, code: int = 400):
        dest.unlink(missing_ok=True)
        return jsonify(ok=False, error=msg), code

    try:
        text = resume_loader.load(ROOT)
    except Exception as e:  # noqa: BLE001
        return _reject(f"Could not read the file: {e}")
    if len(text) < 60:
        return _reject(
            "Resume looks empty or unreadable. If you uploaded a PDF/DOCX, "
            "make sure the optional readers are installed "
            "(`pip install pypdf python-docx`)."
        )

    return jsonify(ok=True, filename=dest.name, chars=len(text),
                   next=_wizard_next("resume"))


@app.post("/api/setup/credentials")
def api_setup_credentials():
    data = request.get_json(force=True, silent=True) or {}
    env = _env_kv()

    for key in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "TO_EMAIL",
                "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_KEY",
                "GROQ_API_KEY", "SERPAPI_KEY"):
        if key in data:
            env[key] = str(data[key] or "").strip()

    gmail_user = env.get("GMAIL_USER", "").strip()
    gmail_pw = env.get("GMAIL_APP_PASSWORD", "").strip()
    to_email = env.get("TO_EMAIL", "").strip() or gmail_user
    if not gmail_user or "@" not in gmail_user:
        return jsonify(ok=False, error="Gmail address is required"), 400
    if not gmail_pw or len(gmail_pw.replace(" ", "")) < 12:
        return jsonify(ok=False,
                       error="Gmail App Password is required (16 chars, no spaces)"), 400

    env["GMAIL_USER"] = gmail_user
    env["GMAIL_APP_PASSWORD"] = gmail_pw.replace(" ", "")
    env["TO_EMAIL"] = to_email

    _write_env(env)
    return jsonify(ok=True, next=_wizard_next("credentials"))


# ── in-process scheduler ───────────────────────────────────────────────────
def _start_scheduler() -> None:
    cfg = _load_config().get("scheduler") or {}
    if not cfg.get("enabled", True):
        log.info("in-process scheduler disabled in config.yaml")
        return
    if os.getenv("JOBSCOUT_NO_SCHEDULER"):
        log.info("in-process scheduler disabled via JOBSCOUT_NO_SCHEDULER")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("APScheduler not installed; in-process scheduling disabled")
        return

    hours = str(cfg.get("hours", "0,6,12,18"))
    minute = int(cfg.get("minute", 20))

    def _job():
        if _run_state["running"]:
            log.info("scheduler tick: previous run still going, skipping")
            return
        log.info("scheduler tick: firing run_once()")
        _run_scout_inprocess(no_email=False)

    with _scheduler_lock:
        if _scheduler_ref["sched"] is not None:
            return
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(_job, trigger=CronTrigger(hour=hours, minute=minute),
                      id="jobscout-cron", replace_existing=True)
        sched.start()
        _scheduler_ref["sched"] = sched
        log.info("in-process scheduler started (hours=%s minute=%d)", hours, minute)


def _toggle_scheduler_pause() -> bool:
    """Pause / resume the scheduler. Returns True if now paused."""
    with _scheduler_lock:
        sched = _scheduler_ref["sched"]
        if sched is None:
            return False
        if _scheduler_ref["paused"]:
            sched.resume()
            _scheduler_ref["paused"] = False
            log.info("scheduler resumed")
            return False
        sched.pause()
        _scheduler_ref["paused"] = True
        log.info("scheduler paused")
        return True


def _shutdown_scheduler() -> None:
    with _scheduler_lock:
        sched = _scheduler_ref["sched"]
        if sched is not None:
            sched.shutdown(wait=False)
            _scheduler_ref["sched"] = None


# ── boot ───────────────────────────────────────────────────────────────────
def _bind() -> tuple[str, int]:
    """Read host/port from env first (JOBSCOUT_HOST/JOBSCOUT_PORT), then config."""
    cfg = _load_config().get("web") or {}
    host = os.getenv("JOBSCOUT_HOST", cfg.get("host") or "127.0.0.1")
    port = int(os.getenv("JOBSCOUT_PORT", cfg.get("port") or 8000))
    return host, port


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Job Scout web UI")
    p.add_argument("--tray", action="store_true", help="also show a system tray icon")
    p.add_argument("--no-scheduler", action="store_true",
                   help="skip the in-process 6-hourly scheduler")
    return p.parse_args()


def _run_flask(host: str, port: int) -> None:
    app.run(host=host, port=port, debug=False, use_reloader=False)


def _run_now_from_tray() -> None:
    if _run_state["running"]:
        return
    threading.Thread(target=_run_scout_inprocess, kwargs={"no_email": False},
                     daemon=True).start()


def main() -> None:
    args = _parse_args()
    store.init_db()
    host, port = _bind()

    if not args.no_scheduler:
        _start_scheduler()

    if args.tray:
        import tray
        flask_thread = threading.Thread(
            target=_run_flask, args=(host, port), daemon=True, name="flask"
        )
        flask_thread.start()
        log.info("Job Scout UI at http://%s:%d  (tray icon active)", host, port)
        try:
            tray.run(
                host, port,
                on_run_now=_run_now_from_tray,
                on_toggle_pause=_toggle_scheduler_pause,
                on_quit=_shutdown_scheduler,
            )
        finally:
            _shutdown_scheduler()
    else:
        log.info("Job Scout UI running at http://%s:%d  (Ctrl+C to stop)", host, port)
        try:
            _run_flask(host, port)
        finally:
            _shutdown_scheduler()


if __name__ == "__main__":
    main()
