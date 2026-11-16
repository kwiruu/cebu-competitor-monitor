"""One scrape run: read the competitor list, fetch pages, store snapshots, detect changes.

    python -m monitor.run            # full run, writes to the database
    python -m monitor.run --dry-run  # fetch and parse only, print what was found
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import find_dotenv, load_dotenv

from . import db, sources
from .fetch import PoliteFetcher
from .parsers import parse_offers


def main(argv=None) -> int:
    args = argparse.ArgumentParser()
    args.add_argument("--dry-run", action="store_true", help="do not touch the database")
    args.add_argument("--csv", action="store_true", help="read competitors.csv even if a sheet is set")
    opts = args.parse_args(argv)

    env_file = find_dotenv(usecwd=True)
    load_dotenv(env_file)
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if key_file and env_file and not os.path.isabs(key_file):
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = os.path.join(os.path.dirname(env_file), key_file)

    rows, source = (sources.from_csv(), "competitors.csv") if opts.csv else sources.load()
    rows = [r for r in rows if r.active]
    print(f"{len(rows)} active pages from {source}")

    conn = run_id = None
    page_ids = {}
    if not opts.dry_run:
        conn = db.connect(os.environ["DATABASE_URL"])
        db.apply_schema(conn)
        page_ids = db.sync_sources(conn, rows)
        run_id = db.start_run(conn)
        print(f"run {run_id} started")

    fetcher = PoliteFetcher()
    pages_ok = pages_failed = 0
    try:
        for row in rows:
            result = fetcher.get(row.page_url, row.crawl_delay_s)
            offers = parse_offers(result.html, row.page_url) if result.ok else []
            if result.ok:
                pages_ok += 1
            else:
                pages_failed += 1
            print(f"  [{'ok' if result.ok else 'FAIL'}] {row.name}: {len(offers)} offers  {row.page_url}"
                  + (f"  ({result.error})" if result.error else ""))
            for o in offers:
                high = f" to {o.price_high:,.0f}" if o.price_high else ""
                print(f"        {o.currency} {o.price:,.0f}{high}  {o.raw_name}")
            if conn:
                page_id, competitor_id = page_ids[row.page_url]
                db.save_page(conn, run_id, page_id, competitor_id, result.http_status, result.ok,
                             offers, result.error)
    finally:
        fetcher.close()

    if conn:
        changes = db.detect_changes(conn, run_id)
        status = db.finish_run(conn, run_id, pages_ok, pages_failed)
        print(f"run {run_id} finished: {status}, {len(changes)} changes")
        for c in changes:
            print(f"  {c['change_type']}: {c['competitor']} / {c['offer']}  {c['old_value']} -> {c['new_value']}")
        conn.close()
    return 0 if pages_ok else 1


if __name__ == "__main__":
    sys.exit(main())
