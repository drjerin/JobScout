# Job Scout

A small program that runs on your laptop, finds jobs matching your resume
across multiple job boards, and emails you a digest — one table per country
you're targeting, each row scored by **% match** with an **Apply** link.

- **Free.** No paid services, no credit card.
- **Private.** Your resume is embedded locally and never leaves the laptop.
- **Transparent.** The % match = resume similarity + an editable checklist.
  No black-box learning; you control it by editing `matching.yaml`.
- **Cross-platform.** One installer works on macOS, Windows, and Linux.
- **Why the laptop (not the cloud):** reliable LinkedIn results need a home
  IP — cloud servers get blocked. Running locally is what makes LinkedIn work.

---

## Sources it searches
| Source | How | Coverage |
|--------|-----|----------|
| **LinkedIn, Indeed, Naukri, Bayt** | JobSpy (scraped from this laptop) | Naukri auto-used for India-style regions, Bayt for Gulf regions, Indeed/LinkedIn everywhere |
| **Jooble** | free API | broad international coverage |
| **Adzuna** | free API | ~20 countries, see their docs |
| **Google Jobs** *(optional)* | SerpApi free tier | extra local boards + some LinkedIn |

Any source with a missing key is simply skipped — the scout still runs.

---

## Quick start

You need **Python 3.10+**. Check with `python3 --version` (macOS/Linux) or
`python --version` (Windows).

```bash
python setup.py install       # creates .venv and installs deps
python app.py                 # opens on http://127.0.0.1:8000
```

Open the URL — the first time, you're routed through a 4-step setup wizard:

1. **Profile** — your name and the role you want to search for.
2. **Locations** — pick countries + cities from a curated list (or type your own).
3. **Resume** — drag-drop a `.pdf`, `.docx`, or `.txt`.
4. **Credentials** — Gmail (required for sending the digest) + optional Adzuna
   and Jooble keys.

That's it. Hit **Run now** on the dashboard to trigger the first scan; the
in-process scheduler will keep running every 6 hours while `app.py` is up.

Prefer the CLI? Edit `config.yaml`, `matching.yaml`, `.env` and your resume file
directly, then:

```bash
python run.py --dry-run   # writes digest_preview.html — no email
python run.py             # sends the real digest
```

If a source returns nothing, the log (`state/scout.log`) says which and why.
The remaining sources still work.

---

## Web UI

A local dashboard to browse everything that doesn't fit in an email — all
matches, with filtering, search, per-country counts, and history.

```bash
python app.py                 # normal
python app.py --tray          # + system-tray icon (needs `install-tray`)
python app.py --no-scheduler  # skip the in-process 6-hourly job
```

Then open **http://127.0.0.1:8000**.

- Sortable tables per country (Match %, Most recent, Company).
- **Search + filter** by New / Applied / Hidden / All.
- **✓ Applied / Undo / Hide / Unhide** buttons per row (remembered in
  `state/jobs.db`).
- **↻ Run now** — trigger a fresh scan on demand and see the log tail inline.
- **Settings** tab — edit `config.yaml` and `matching.yaml` in the browser
  (YAML-validated before saving), or re-run the wizard any time.

Override the bind address with `JOBSCOUT_HOST`/`JOBSCOUT_PORT` env vars, or
`web.host`/`web.port` in `config.yaml`.

The scheduled email and the UI share the same SQLite database, so anything
the scout finds shows up in both. Leave `app.py` running (or start it when
you want to browse).

### System tray icon (optional)

```bash
python setup.py install-tray        # installs pystray + Pillow
python setup.py install-autostart   # run app.py --tray at login (all 3 OSes)
python app.py --tray                # start now
```

The tray icon exposes **Open Dashboard**, **Run now**, **Pause/Resume schedule**,
and **Quit**.

---

## Run it every 6 hours automatically

Two options — pick whichever fits your workflow:

**In-process scheduler (default)** — comes on when you run `python app.py`.
No extra setup, but only runs while the UI process is alive. Configurable
via the `scheduler:` block in `config.yaml`.

**OS scheduler** — runs on a fixed schedule even when nothing is open:

```bash
python setup.py install-scheduler       # macOS launchd / Windows Task Scheduler / Linux cron
python setup.py remove-scheduler        # undo
```

Manual instructions per platform are in [`scheduler/README.md`](scheduler/README.md).
The laptop must be on/awake at the scheduled times; missed runs harmlessly
catch up on the next one.

---

## .env keys

The setup wizard writes these for you, but you can edit `.env` directly:

- **Email (required)** — `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `TO_EMAIL`.
  On the Google account: enable **2-Step Verification**, then create an
  **App Password** (Google Account → Security → App passwords) and paste the
  16-character value.
- **Adzuna (recommended)** — instant free `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`
  at https://developer.adzuna.com/
- **Jooble (recommended, broad country coverage)** — free key at
  https://jooble.org/api/about
- **Optional** — `GROQ_API_KEY` (https://console.groq.com) adds a one-line
  "why it fits" note; `SERPAPI_KEY` (https://serpapi.com) adds Google Jobs.
  Both fine to leave blank.

Not a Gmail user? Any SMTP provider works — swap the SMTP call in
`email_report.py`.

---

## Good to know (honest caveats)
- **LinkedIn scraping is a gray area.** This is personal, low-volume,
  logged-out use from a home IP — the low-risk zone. Don't scrape while
  logged into a LinkedIn account. It will occasionally break when LinkedIn
  changes things; the other sources keep the digest useful in the meantime.
- **Descriptions vary.** Indeed/Naukri are full text (best matching);
  Jooble/Adzuna/Bayt are snippets. The matching checklist fills the gap.
- **No repeats.** Each digest only shows jobs it hasn't emailed before
  (tracked in `state/jobs.db`). To hide a company/title, add it to the
  exclude lists in `matching.yaml`.
- **Free tiers change.** If a source stops returning results, check its
  console/key.

---

## How the % match works
```
match% = resume_weight · resume_similarity%  +  matching_weight · checklist%
```
- **resume_similarity** — how close the job text is to your resume (local
  embeddings).
- **checklist** — target-title match, must-have skills present, seniority
  band, nice-to-haves.
- Shown per row as the number + ✅/⚠️ **Fit notes**. Adjust the weights in
  `config.yaml`.

---

## Project map
```
run.py            orchestrator (fetch → dedupe → filter → score → split → store → email)
                  exposes run_once() for the UI / scheduler to call in-process
app.py            Flask UI: dashboard, /setup wizard, resume upload, APScheduler
setup.py          cross-platform installer, scheduler + tray helper
store.py          SQLite store shared by run.py + app.py (dedupe memory + history)
tray.py           optional system-tray icon (pystray)
locations.py      curated country + city catalog for the wizard
config.yaml       profile, search terms, countries, thresholds, source toggles, web bind
matching.yaml     editable checklist + dealbreakers
resume.txt        your resume (plain text) — pdf/docx also supported
.env              your keys (never commit)
sources/          one adapter per job board/API
embed.py          local sentence-transformers embeddings (bge-small-en-v1.5)
score.py          transparent scoring
email_report.py   HTML/plain-text digest + Gmail sending
rationale.py      optional Groq "why it fits" line
resume_loader.py  read resume from .txt / .pdf / .docx
http_client.py    shared requests session with retry/backoff
logs.py           rotating file + stdout logging
templates/        web UI pages (base / dashboard / settings / setup)
scheduler/        cross-platform scheduling (launchd / Task Scheduler / cron)
state/            SQLite DB + rotated logs (gitignored)
tests/            pytest suite (score / store / sources)
```

---

## Contributing / tests

```bash
pip install -e ".[dev]"
pytest              # runs the small unit-test suite
ruff check .        # lint
```

Licensed under the MIT License — see [LICENSE](LICENSE).
