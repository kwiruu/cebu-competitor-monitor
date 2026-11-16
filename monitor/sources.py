"""Read the competitor list. The Google Sheet is the front door; the CSV is the fallback.

Both use the same columns:
name, website, page_url, page_type, is_us, crawl_delay_s, active
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ["name", "website", "page_url", "page_type", "is_us", "crawl_delay_s", "active"]
CSV_PATH = Path(__file__).resolve().parent.parent / "competitors.csv"


@dataclass(frozen=True)
class PageRow:
    name: str
    website: str
    page_url: str
    page_type: str
    is_us: bool
    crawl_delay_s: int
    active: bool


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "yes", "y", "1"}


def _to_row(raw: dict) -> PageRow | None:
    name, url = str(raw.get("name", "")).strip(), str(raw.get("page_url", "")).strip()
    if not name or not url.startswith("http"):
        return None
    delay = str(raw.get("crawl_delay_s", "")).strip()
    return PageRow(
        name=name,
        website=str(raw.get("website", "")).strip().rstrip("/"),
        page_url=url,
        page_type=str(raw.get("page_type", "")).strip() or "package",
        is_us=_truthy(raw.get("is_us", "")),
        crawl_delay_s=int(delay) if delay.isdigit() else 1,
        active=_truthy(raw.get("active", "true") or "true"),
    )


def from_csv(path: Path = CSV_PATH) -> list[PageRow]:
    with open(path, newline="", encoding="utf-8") as f:
        return [row for raw in csv.DictReader(f) if (row := _to_row(raw))]


def from_sheet(sheet_id: str, key_file: str, tab: str = "Competitors") -> list[PageRow]:
    import gspread

    client = gspread.service_account(filename=key_file)
    records = client.open_by_key(sheet_id).worksheet(tab).get_all_records()
    return [row for raw in records if (row := _to_row(raw))]


def load() -> tuple[list[PageRow], str]:
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if sheet_id and key_file:
        return from_sheet(sheet_id, key_file), "google sheet"
    return from_csv(), "competitors.csv"
