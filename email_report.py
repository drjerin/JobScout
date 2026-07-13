"""Build and send the HTML email digest.

Sends via Gmail SMTP (app password) with a plain-text fallback. In dry-run,
``run.py`` calls :func:`write_preview` to save the HTML locally instead of
emailing.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

import logs

_log = logs.get("scout.email")

_STATUS_ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌"}

_HTML = Template(
    """
<div style="font-family:Arial,Helvetica,sans-serif;max-width:960px;margin:0 auto;color:#1a1a1a;">
  <h2 style="margin:0 0 2px;">{{ meta.title }}</h2>
  <p style="color:#666;margin:0 0 16px;font-size:13px;">{{ meta.subtitle }}</p>
  {% for name, rows in sections %}
    <h3 style="margin:22px 0 8px;">{{ name }}
      <span style="color:#888;font-weight:normal;font-size:13px;">({{ rows|length }})</span></h3>
    {% if rows %}
    <table role="presentation" width="100%" cellpadding="8" cellspacing="0"
           style="border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f2f4f7;text-align:left;color:#374151;">
          <th style="white-space:nowrap;">Match</th><th>Title</th><th>Company</th>
          <th>Location</th><th style="white-space:nowrap;">Posted</th><th>Source</th>
          <th>Fit notes</th><th>Apply</th>
        </tr>
      </thead>
      <tbody>
      {% for r in rows %}
        <tr style="border-bottom:1px solid #e5e7eb;vertical-align:top;">
          <td style="font-weight:bold;color:{{ r.color }};white-space:nowrap;">{{ r.match }}%</td>
          <td>{{ r.title }}</td>
          <td>{{ r.company }}</td>
          <td style="color:#555;">{{ r.location }}</td>
          <td style="white-space:nowrap;color:#888;">{{ r.posted }}</td>
          <td style="color:#555;">{{ r.source }}</td>
          <td style="color:#374151;">{{ r.notes }}
            {%- if r.why %}<br><span style="color:#6b7280;font-style:italic;">{{ r.why }}</span>{% endif %}</td>
          <td><a href="{{ r.url }}"
                 style="color:#2563eb;font-weight:bold;text-decoration:none;white-space:nowrap;">Apply &rarr;</a></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p style="color:#999;">No new matches this run.</p>
    {% endif %}
  {% endfor %}
  <p style="color:#aaa;font-size:11px;margin-top:26px;">
    Sent by your local Job Scout. Tune matching by editing <code>matching.yaml</code>.
    Jobs already emailed are never repeated.</p>
</div>
""",
    autoescape=True,
)


def _match_color(pct: float) -> str:
    if pct >= 80:
        return "#15803d"   # green
    if pct >= 65:
        return "#b45309"   # amber
    return "#6b7280"       # grey


def _notes_str(fit_notes) -> str:
    return "  ".join(f"{_STATUS_ICON.get(st, '•')} {label}" for st, label in (fit_notes or []))


def _rows(jobs) -> list[dict]:
    out = []
    for j in jobs:
        out.append({
            "match": round(j.match_percent),
            "color": _match_color(j.match_percent),
            "title": j.title or "(untitled)",
            "company": j.company or "—",
            "location": j.location or "—",
            "posted": j.posted or "—",
            "source": j.source,
            "notes": _notes_str(j.fit_notes),
            "why": j.why or "",
            "url": j.url or "#",
        })
    return out


def render_html(sections, meta: dict) -> str:
    prepared = [(name, _rows(jobs)) for name, jobs in sections]
    return _HTML.render(sections=prepared, meta=meta)


def render_text(sections, meta: dict) -> str:
    lines = [meta.get("title", "Job Scout"), meta.get("subtitle", ""), ""]
    for name, jobs in sections:
        lines.append(f"== {name} ({len(jobs)}) ==")
        if not jobs:
            lines.append("  No new matches this run.")
        for j in jobs:
            lines.append(f"  {round(j.match_percent)}%  {j.title} — {j.company} — {j.location} [{j.source}]")
            notes = _notes_str(j.fit_notes)
            if notes:
                lines.append(f"        {notes}")
            lines.append(f"        Apply: {j.url}")
        lines.append("")
    return "\n".join(lines)


def send_email(subject: str, html: str, text: str) -> None:
    user = os.getenv("GMAIL_USER", "").strip()
    pw = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    to = os.getenv("TO_EMAIL", "").strip() or user
    if not (user and pw):
        raise SystemExit("GMAIL_USER / GMAIL_APP_PASSWORD not set in .env — cannot send email.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
        server.login(user, pw)
        server.sendmail(user, [to], msg.as_string())
    _log.info("sent to %s", to)


def write_preview(html: str, path: str = "digest_preview.html") -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    _log.info("dry-run preview written to %s", path)
    return path
