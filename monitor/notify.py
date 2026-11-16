"""Send new tickets to the n8n webhook. n8n decides who hears about them and how.

This module only describes what happened: one plain-language message per change and a
severity, so the n8n workflow can stay simple (high -> Telegram now, low -> weekly digest).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx

RETRY_WAITS_S = (5, 15, 45)   # n8n on a free host may need up to a minute to wake up


def severity(change: dict, threshold_pct: float) -> str:
    if change["change_type"] in ("new_offer", "removed_offer"):
        return "high"
    pct = change.get("pct_change")
    return "high" if pct is not None and abs(float(pct)) >= threshold_pct else "low"


def _money(value) -> str:
    return f"PHP {Decimal(value):,.0f}"


def message(change: dict, us_prices: dict[str, Decimal]) -> str:
    who, offer, kind = change["competitor"], change["offer"], change["change_type"]
    if kind == "price_change":
        verb = "lowered" if change["new_value"] < change["old_value"] else "raised"
        text = (f"{who} {verb} \"{offer}\" from {_money(change['old_value'])} "
                f"to {_money(change['new_value'])} ({float(change['pct_change']):+.1f}%).")
    elif kind == "new_offer":
        text = f"{who} added a new package: \"{offer}\" at {_money(change['new_value'])}."
    else:
        text = f"{who} removed \"{offer}\" (was {_money(change['old_value'])})."

    ours = us_prices.get(change["category"])
    theirs = change.get("new_value")
    if ours is not None and theirs is not None and not change.get("is_us"):
        gap = (Decimal(theirs) - ours) / ours * 100
        side = "cheaper than" if gap < 0 else "more expensive than"
        text += f" That is {abs(gap):.0f}% {side} our cheapest in this category ({_money(ours)})."
    return text


def build_payload(run_id: int, run_status: str, changes: list[dict], failed_pages: list[dict],
                  us_prices: dict[str, Decimal], threshold_pct: float | None = None) -> dict:
    if threshold_pct is None:
        threshold_pct = float(os.getenv("ALERT_THRESHOLD_PCT", "10"))
    return {
        "run_id": run_id,
        "run_status": run_status,
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "failed_pages": failed_pages,
        "changes": [
            {
                "change_id": c["id"],
                "detected_at": c["detected_at"].isoformat(timespec="seconds") if c.get("detected_at") else None,
                "competitor": c["competitor"],
                "offer": c["offer"],
                "category": c["category"],
                "change_type": c["change_type"],
                "old_value": float(c["old_value"]) if c["old_value"] is not None else None,
                "new_value": float(c["new_value"]) if c["new_value"] is not None else None,
                "pct_change": float(c["pct_change"]) if c["pct_change"] is not None else None,
                "severity": severity(c, threshold_pct),
                "message": message(c, us_prices),
                "status": "new",
            }
            for c in changes
        ],
    }


def send(url: str, payload: dict, secret: str = "", client: httpx.Client | None = None,
         sleep=time.sleep) -> bool:
    """POST the payload. Returns True once n8n answers 2xx; retries while it wakes up."""
    client = client or httpx.Client(timeout=60)
    headers = {"X-Monitor-Secret": secret} if secret else {}
    for wait in (*RETRY_WAITS_S, None):
        try:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code < 300:
                return True
            if response.status_code < 500 and response.status_code != 404:
                return False            # our request is wrong; retrying will not help
        except httpx.HTTPError:
            pass
        if wait is not None:
            sleep(wait)
    return False
