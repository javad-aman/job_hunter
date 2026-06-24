# jobhunt

A local-first, automated UI/UX job discovery system.  
Aggregates postings from job boards and company ATS pages, dedupes, scores
against your profile with Claude, and writes a ranked daily digest.

## Quick start

```bash
# 1. Clone / enter the project
cd job_hunt

# 2. Create a virtualenv and install deps
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# edit .env — add your ANTHROPIC_API_KEY at minimum

# 4. Configure your profile and company shortlist
# edit config.yaml — fill in my_profile + companies

# 5. Run
python -m jobhunt
```

Output lands in `output/digest_YYYY-MM-DD.md` and `.csv`.

---

## CLI flags

| Flag | Effect |
|------|--------|
| `--no-email` | Skip sending the email digest |
| `--no-boards` | Skip JobSpy board scraping |
| `--no-ats` | Skip company ATS polling |

---

## How to find ATS tokens

### Greenhouse
Visit the company's job board URL, e.g. `https://boards.greenhouse.io/figma`.  
The slug after `/` is the token → `figma`.

### Lever
Visit `https://jobs.lever.co/COMPANY`.  
The slug is the token → `COMPANY`.

### Ashby
Visit `https://jobs.ashbyhq.com/COMPANY`.  
The slug is the token → `COMPANY`.

---

## Scheduling locally (cron)

Add this line to your crontab (`crontab -e`) to run at 8 AM daily:

```
0 8 * * * cd /path/to/job_hunt && /path/to/.venv/bin/python -m jobhunt >> /tmp/jobhunt.log 2>&1
```

On Windows, use Task Scheduler pointing to `pythonw.exe -m jobhunt`.

---

## Architecture

```
fetch (concurrent asyncio)
  ├─ boards.py        → JobSpy (Indeed / Glassdoor / Google)
  ├─ greenhouse.py    → Greenhouse ATS REST API
  ├─ lever.py         → Lever ATS REST API
  └─ ashby.py         → Ashby ATS REST API
        ↓
normalizer.py         → coerce to Posting dataclass
deduper.py            → URL + title+company dedup
seen_store.py         → SQLite filter (skip previously seen URLs)
scorer.py             → Claude LLM, batched, JSON output
        ↓
digest.py             → output/digest_YYYY-MM-DD.md + .csv
email_sender.py       → optional SMTP delivery
```

---

## Config reference (`config.yaml`)

| Key | Description |
|-----|-------------|
| `my_profile` | Your background / preferences — the LLM scoring rubric |
| `search.terms` | Job-board search terms |
| `search.location` | City / region for board searches |
| `search.is_remote` | Include remote postings in board results |
| `search.hours_old` | Only fetch postings newer than N hours |
| `search.results_wanted` | Postings to fetch per board per search term |
| `search.boards` | Which JobSpy boards to query |
| `ats_title_keywords` | Title filter applied to all ATS results |
| `companies` | List of `{name, ats, token}` to poll |
| `digest.top_n` | Max postings in the digest |
| `digest.min_score` | Drop postings below this score |
| `llm.model` | Claude model to use for scoring |
| `llm.batch_size` | Postings per LLM API call |
