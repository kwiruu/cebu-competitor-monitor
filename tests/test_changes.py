"""Change detection against a real Postgres. Runs when TEST_DATABASE_URL is set (CI sets it)."""
import os
from decimal import Decimal

import psycopg
import pytest

from monitor import db
from monitor.parsers import Offer
from monitor.sources import PageRow

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

PAGE = "https://a.test/tours"
ROW = PageRow("Alpha Tours", "https://a.test", PAGE, "package", False, 1, True)


@pytest.fixture
def conn():
    with psycopg.connect(URL) as c:
        c.execute("drop schema if exists public cascade; create schema public;")
        db.apply_schema(c)
        yield c


def run(conn, offers, ok=True):
    page_id, competitor_id = db.sync_sources(conn, [ROW])[PAGE]
    run_id = db.start_run(conn)
    db.save_page(conn, run_id, page_id, competitor_id, 200 if ok else 500, ok, offers, None)
    return [(c["change_type"], c["offer"], c["old_value"], c["new_value"]) for c in db.detect_changes(conn, run_id)]


def offer(name, price):
    return Offer(name, Decimal(price), None, "PHP")


def test_first_run_creates_no_tickets(conn):
    assert run(conn, [offer("Island Hopping", "3000")]) == []


def test_price_change_new_and_removed(conn):
    run(conn, [offer("Island Hopping", "3000"), offer("City Tour", "1500")])
    changes = run(conn, [offer("Island Hopping", "2700"), offer("Canyoneering", "2100")])
    assert sorted(changes) == [
        ("new_offer", "Canyoneering", None, Decimal("2100.00")),
        ("price_change", "Island Hopping", Decimal("3000.00"), Decimal("2700.00")),
        ("removed_offer", "City Tour", Decimal("1500.00"), None),
    ]
    pct = conn.execute("select pct_change from changes where change_type = 'price_change'").fetchone()[0]
    assert pct == Decimal("-10.00")


def test_unchanged_price_creates_no_ticket(conn):
    run(conn, [offer("Island Hopping", "3000")])
    assert run(conn, [offer("Island Hopping", "3000")]) == []


def test_failed_page_is_not_reported_as_removed(conn):
    run(conn, [offer("Island Hopping", "3000")])
    assert run(conn, [], ok=False) == []
    # When the page loads again at a new price, compare with the last good run.
    assert run(conn, [offer("Island Hopping", "3300")]) == [
        ("price_change", "Island Hopping", Decimal("3000.00"), Decimal("3300.00"))
    ]


def test_renamed_offer_keeps_its_history(conn):
    run(conn, [offer("Island Hopping Joiner Tour 2026", "3000")])
    assert run(conn, [offer("Island Hopping Joiner Tour 2027", "3200")]) == [
        ("price_change", "Island Hopping Joiner Tour 2026", Decimal("3000.00"), Decimal("3200.00"))
    ]
