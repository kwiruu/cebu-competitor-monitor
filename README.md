# Cebu Competitor Monitor

**Status: work in progress.** Collection, snapshots and change detection are built. The n8n alert workflows are drafted but not yet tested. The GEO readiness score, the weekly brief and the dashboard are not built yet.

## The question

A Cebu tour operator wants to know: what are my competitors charging, what changed since yesterday, and does it matter to me? Checking six websites by hand every day does not happen. This tool does it and turns each change into a ticket someone can act on.

The operator in this project is a scenario, not a real client.

## How it works

1. **Intake.** An ops person lists competitor pages in a Google Sheet (`competitors.csv` is the fallback with the same columns). One row can be marked `is_us`.
2. **Collect.** A daily GitHub Actions job fetches each page.
3. **Store.** Every run adds new snapshot rows to Postgres (Supabase). Nothing is overwritten.
4. **Detect.** SQL window functions compare the run with earlier runs and write tickets: price change, new offer, removed offer.
5. **Route (drafted).** The scraper posts tickets to n8n, which sends big changes to Telegram at once and the rest to a weekly digest.

## Scraping rules

- Public pages only. No logins, no personal data.
- robots.txt is read first and obeyed, including crawl delays.
- At least one second between requests to the same site.
- The bot names itself in the User-Agent.
- Only facts are stored: package name and price. No descriptions or images.

## Run it

```bash
pip install -r requirements.txt
python -m monitor.run --dry-run --csv   # fetch and parse only
python -m monitor.run                   # full run, needs DATABASE_URL
pytest -q
```

Copy `.env.example` to `.env` for the settings. Database tests run when `TEST_DATABASE_URL` is set, which CI does.

## Layout

| Path | What it is |
|---|---|
| `monitor/sources.py` | Reads the competitor list from the sheet or the CSV |
| `monitor/fetch.py` | Polite fetcher (robots.txt, delays) |
| `monitor/parsers.py` | Finds package names and prices: schema.org JSON-LD first, per-person price text second |
| `monitor/matching.py` | Fuzzy matching for a stable offer identity, and activity tags to compare across competitors |
| `monitor/db.py` | Database writes for a run |
| `sql/001_schema.sql` | Tables and views |
| `sql/detect_changes.sql` | Change detection with `LAG` and `ROW_NUMBER` |
