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
python setup.py install
```

That creates a virtualenv, installs dependencies, copies the `.env` and
`resume.txt` templates, and creates the `state/` directory.

Then:

1. **Edit `.env`** with your email + API keys (see below).
2. **Drop your resume** into the project root — `resume.txt`, `resume.pdf`,
   or `resume.docx` all work (the last two need `pip install pypdf` /
   `pip install python-docx`).
3. **Tune the search** by editing `config.yaml` (search terms, countries,
   thresholds) and `matching.yaml` (target titles, seniority band, must-have
   skills, dealbreakers).

Try it:

```bash
# Activate the venv first (once per shell):
#   macOS/Linux :   source .venv/bin/activate
#   Windows     :   .venv\Scripts\activate

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
python app.py
```

Then open **http://127.0.0.1:8000**.

- Sortable tables per country (Match %, Most recent, Company).
- **Search + filter** by New / Applied / Hidden / All.
- **✓ Applied / Undo / Hide / Unhide** buttons per row (remembered in
  `state/jobs.db`).
- **↻ Run now** — trigger a fresh scan on demand and see the log tail inline.
- **Settings** tab — edit `config.yaml` and `matching.yaml` in the browser
  (YAML-validated before saving).

Override the bind address with `JOBSCOUT_HOST`/`JOBSCOUT_PORT` env vars, or
`web.host`/`web.port` in `config.yaml`.

The scheduled email and the UI share the same SQLite database, so anything
the scout finds shows up in both. Leave `app.py` running (or start it when
you want to browse).

---

## Run it every 6 hours automatically

The installer handles this on all three platforms:

```bash
python setup.py install-scheduler       # macOS launchd / Windows Task Scheduler / Linux cron
python setup.py remove-scheduler        # undo
```

Manual instructions per platform are in [`scheduler/README.md`](scheduler/README.md).
The laptop must be on/awake at the scheduled times; missed runs harmlessly
catch up on the next one.

---

## .env keys

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
app.py            local web dashboard (Flask): browse/filter, run-now, edit settings
setup.py          cross-platform installer + scheduler helper
store.py          SQLite store shared by run.py + app.py (dedupe memory + history)
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
templates/        web UI pages (base / dashboard / settings)
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
