#!/usr/bin/env python3
"""Cross-platform installer / helper for Job Scout.

Subcommands:
    python setup.py install            # create .venv and install deps
    python setup.py install-scheduler  # register the 6-hourly job (OS-aware)
    python setup.py remove-scheduler   # unregister it
    python setup.py doctor             # print environment diagnostics

Everything is idempotent and safe to re-run.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _venv_python() -> Path:
    return VENV_DIR / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")


def _run(cmd: list[str], **kw) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    subprocess.check_call(cmd, **kw)


# ── install (venv + deps) ─────────────────────────────────────────────────
def install() -> None:
    if not VENV_DIR.exists():
        print(f"[+] creating virtualenv at {VENV_DIR}")
        _run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        print(f"[=] virtualenv already exists at {VENV_DIR}")

    py = _venv_python()
    if not py.exists():
        raise SystemExit(f"venv python not found at {py}")

    print("[+] installing dependencies")
    _run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(py), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])

    env_example = ROOT / ".env.example"
    env_file = ROOT / ".env"
    if env_example.exists() and not env_file.exists():
        shutil.copy(env_example, env_file)
        print("[+] copied .env.example -> .env  (edit it to add your keys)")

    resume_example = ROOT / "resume.txt.example"
    resume_file = ROOT / "resume.txt"
    resume_any = any((ROOT / n).exists() for n in ("resume.txt", "resume.pdf", "resume.docx"))
    if resume_example.exists() and not resume_any:
        shutil.copy(resume_example, resume_file)
        print("[+] created resume.txt from template  (replace with your resume)")

    (ROOT / "state").mkdir(exist_ok=True)
    print("\nDone. Next steps:")
    print("  1. Edit .env with your keys/email details.")
    print("  2. Drop your resume into resume.txt (or resume.pdf / resume.docx).")
    print("  3. Try:  python run.py --dry-run")


# ── scheduler ─────────────────────────────────────────────────────────────
def install_scheduler() -> None:
    if IS_MAC:
        _install_mac()
    elif IS_WINDOWS:
        _install_windows()
    elif IS_LINUX:
        _install_linux()
    else:
        raise SystemExit(f"Unsupported OS: {platform.system()}")


def remove_scheduler() -> None:
    if IS_MAC:
        _remove_mac()
    elif IS_WINDOWS:
        _remove_windows()
    elif IS_LINUX:
        _remove_linux()
    else:
        raise SystemExit(f"Unsupported OS: {platform.system()}")


def _install_mac() -> None:
    plist_src = ROOT / "scheduler" / "com.jobscout.plist"
    plist_dst = Path.home() / "Library" / "LaunchAgents" / "com.jobscout.plist"
    plist_dst.parent.mkdir(parents=True, exist_ok=True)

    content = plist_src.read_text(encoding="utf-8").replace("__PROJECT_DIR__", str(ROOT))
    plist_dst.write_text(content, encoding="utf-8")
    os.chmod(ROOT / "scheduler" / "run.sh", 0o755)

    subprocess.call(["launchctl", "unload", str(plist_dst)])  # ignore first-time failure
    _run(["launchctl", "load", str(plist_dst)])
    print(f"[+] installed LaunchAgent at {plist_dst}")
    print("    Test:   launchctl start com.jobscout && tail -f state/scout.log")
    print("    Remove: python setup.py remove-scheduler")


def _remove_mac() -> None:
    plist = Path.home() / "Library" / "LaunchAgents" / "com.jobscout.plist"
    if plist.exists():
        subprocess.call(["launchctl", "unload", str(plist)])
        plist.unlink()
        print(f"[+] removed {plist}")
    else:
        print(f"[=] no LaunchAgent installed at {plist}")


def _install_windows() -> None:
    bat = ROOT / "scheduler" / "run.bat"
    cmd = [
        "schtasks", "/create", "/f",
        "/tn", "JobScout",
        "/tr", f'"{bat}"',
        "/sc", "HOURLY",
        "/mo", "6",
        "/st", "00:20",
    ]
    _run(cmd)
    print("[+] installed Windows scheduled task 'JobScout'")
    print("    Tip: in Task Scheduler > JobScout > Settings, tick")
    print("         'Run task as soon as possible after a scheduled start is missed'")
    print("    Test:   schtasks /run /tn JobScout")
    print("    Remove: python setup.py remove-scheduler")


def _remove_windows() -> None:
    _run(["schtasks", "/delete", "/tn", "JobScout", "/f"])
    print("[+] removed Windows scheduled task 'JobScout'")


def _install_linux() -> None:
    run_sh = ROOT / "scheduler" / "run.sh"
    os.chmod(run_sh, 0o755)
    cron_line = f"20 */6 * * * {run_sh}"
    existing = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    ).stdout or ""
    if str(run_sh) in existing:
        print(f"[=] cron already contains: {cron_line}")
        return
    new_cron = (existing.rstrip() + "\n" + cron_line + "\n").lstrip()
    proc = subprocess.run(["crontab", "-"], input=new_cron, text=True)
    if proc.returncode == 0:
        print(f"[+] added cron entry: {cron_line}")
    else:
        raise SystemExit("Could not install cron entry — install manually.")


def _remove_linux() -> None:
    run_sh = str(ROOT / "scheduler" / "run.sh")
    existing = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    ).stdout or ""
    filtered = "\n".join(line for line in existing.splitlines() if run_sh not in line)
    if filtered.strip():
        filtered += "\n"
    subprocess.run(["crontab", "-"], input=filtered, text=True, check=True)
    print("[+] cron entries pointing at run.sh removed")


# ── doctor ────────────────────────────────────────────────────────────────
def doctor() -> None:
    print(f"platform      : {platform.system()} {platform.release()}")
    print(f"python        : {sys.version.split()[0]} ({sys.executable})")
    print(f"project root  : {ROOT}")
    print(f"venv          : {VENV_DIR} {'(present)' if VENV_DIR.exists() else '(MISSING)'}")
    for name in (".env", "config.yaml", "matching.yaml"):
        p = ROOT / name
        print(f"  {name:<14}: {'ok' if p.exists() else 'MISSING'}")
    resume = next((ROOT / n for n in ("resume.txt", "resume.pdf", "resume.docx") if (ROOT / n).exists()), None)
    print(f"  resume        : {'ok (' + resume.name + ')' if resume else 'MISSING'}")


# ── entry point ───────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Job Scout installer / helper")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("install", help="create .venv and install requirements")
    sub.add_parser("install-scheduler", help="register the OS scheduler entry")
    sub.add_parser("remove-scheduler", help="unregister the OS scheduler entry")
    sub.add_parser("doctor", help="print environment diagnostics")
    args = parser.parse_args()

    cmd = args.cmd or "install"
    {
        "install": install,
        "install-scheduler": install_scheduler,
        "remove-scheduler": remove_scheduler,
        "doctor": doctor,
    }[cmd]()


if __name__ == "__main__":
    main()
