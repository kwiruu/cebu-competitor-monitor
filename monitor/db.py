"""All database writes for one scrape run."""
from __future__ import annotations

from pathlib import Path

import psycopg

from .matching import categorize, match_existing
from .parsers import Offer
from .sources import PageRow

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, connect_timeout=30)


def apply_schema(conn: psycopg.Connection):
    conn.execute((SQL_DIR / "001_schema.sql").read_text(encoding="utf-8"))
    conn.commit()


def sync_sources(conn: psycopg.Connection, rows: list[PageRow]) -> dict[str, tuple[int, int]]:
    """Upsert competitors and pages. Returns page_url -> (page_id, competitor_id)."""
    ids: dict[str, tuple[int, int]] = {}
    for row in rows:
        competitor_id = conn.execute(
            """insert into competitors (name, website, is_us, crawl_delay_s, active)
               values (%s, %s, %s, %s, true)
               on conflict (website) do update
                 set name = excluded.name, is_us = excluded.is_us, crawl_delay_s = excluded.crawl_delay_s
               returning id""",
            (row.name, row.website, row.is_us, row.crawl_delay_s),
        ).fetchone()[0]
        page_id = conn.execute(
            """insert into pages (competitor_id, url, page_type, active)
               values (%s, %s, %s, %s)
               on conflict (url) do update set page_type = excluded.page_type, active = excluded.active
               returning id""",
            (competitor_id, row.page_url, row.page_type, row.active),
        ).fetchone()[0]
        ids[row.page_url] = (page_id, competitor_id)
    conn.commit()
    return ids


def start_run(conn: psycopg.Connection) -> int:
    run_id = conn.execute("insert into scrape_runs default values returning id").fetchone()[0]
    conn.commit()
    return run_id


def save_page(conn, run_id: int, page_id: int, competitor_id: int, http_status, ok: bool,
              offers: list[Offer], error: str | None):
    conn.execute(
        """insert into page_fetches (run_id, page_id, http_status, ok, offers_found, error)
           values (%s, %s, %s, %s, %s, %s)""",
        (run_id, page_id, http_status, ok, len(offers), error),
    )
    existing = [r[0] for r in conn.execute(
        "select canonical_name from offers where competitor_id = %s", (competitor_id,))]
    for offer in offers:
        canonical = match_existing(offer.raw_name, existing) or offer.raw_name
        offer_id = conn.execute(
            """insert into offers (competitor_id, canonical_name, category)
               values (%s, %s, %s)
               on conflict (competitor_id, canonical_name) do update set category = excluded.category
               returning id""",
            (competitor_id, canonical, categorize(canonical)),
        ).fetchone()[0]
        if canonical not in existing:
            existing.append(canonical)
        conn.execute(
            """insert into offer_snapshots (run_id, offer_id, page_id, raw_name, price, price_high, currency)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (run_id, offer_id) do nothing""",
            (run_id, offer_id, page_id, offer.raw_name, offer.price, offer.price_high, offer.currency),
        )
    conn.commit()


def detect_changes(conn: psycopg.Connection, run_id: int) -> list[dict]:
    sql = (SQL_DIR / "detect_changes.sql").read_text(encoding="utf-8")
    for statement in [s for s in sql.split(";") if s.strip() and not _only_comments(s)]:
        conn.execute(statement, {"run_id": run_id})
    conn.commit()
    return _tickets(conn, "ch.run_id = %s", (run_id,))


def _tickets(conn, where: str, params: tuple) -> list[dict]:
    cur = conn.execute(
        f"""select ch.id, c.name as competitor, c.is_us, o.canonical_name as offer, o.category,
                   ch.change_type, ch.old_value, ch.new_value, ch.pct_change, ch.detected_at
            from changes ch
            join competitors c on c.id = ch.competitor_id
            join offers o on o.id = ch.offer_id
            where {where}
            order by ch.id""",
        params,
    )
    columns = [d.name for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def pending_tickets(conn) -> list[dict]:
    """Tickets n8n has not accepted yet, including any left over from an earlier run."""
    return _tickets(conn, "ch.notified_at is null", ())


def mark_notified(conn, change_ids: list[int]):
    conn.execute("update changes set notified_at = now() where id = any(%s)", (change_ids,))
    conn.commit()


def us_prices(conn) -> dict:
    """Our own cheapest current price per category (rows flagged is_us)."""
    rows = conn.execute(
        "select category, min(price) from v_latest_prices where is_us and currency = 'PHP' group by category")
    return dict(rows.fetchall())


def failed_pages(conn, run_id: int) -> list[dict]:
    rows = conn.execute(
        """select c.name, p.url, pf.error from page_fetches pf
           join pages p on p.id = pf.page_id join competitors c on c.id = p.competitor_id
           where pf.run_id = %s and not pf.ok order by p.id""", (run_id,))
    return [{"competitor": r[0], "url": r[1], "error": r[2]} for r in rows.fetchall()]


def _only_comments(statement: str) -> bool:
    return all(line.strip().startswith("--") or not line.strip() for line in statement.splitlines())


def finish_run(conn: psycopg.Connection, run_id: int, pages_ok: int, pages_failed: int):
    status = "ok" if pages_failed == 0 else ("partial" if pages_ok else "failed")
    conn.execute("update scrape_runs set finished_at = now(), status = %s where id = %s", (status, run_id))
    conn.commit()
    return status
