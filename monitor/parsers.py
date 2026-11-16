"""Turn a page's HTML into a list of offers (package name + price).

Two strategies, tried in order, so a new competitor usually needs no new code:
1. JSON-LD: schema.org data the site publishes for search engines.
2. Per-person text: lines such as "2 guests: ₱5,050 per person".
"""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Offer:
    raw_name: str
    price: Decimal                 # lowest listed price
    price_high: Decimal | None     # highest listed price, when tiered
    currency: str = "PHP"


_PESO = re.compile(r"(?:₱|PHP|Php|php)\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?")
_PER_PERSON = re.compile(r"per\s+person|per\s+pax|/\s?pax|\bpax\b|guests?\b", re.I)
_PRODUCT_TYPES = {"Product", "TouristTrip", "Trip", "Service"}


def parse_offers(html: str, page_url: str) -> list[Offer]:
    soup = BeautifulSoup(html, "lxml")
    return _from_jsonld(soup, page_url) or _from_per_person_text(soup)


def _to_decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return number if number > 0 else None


def _clean_name(name: str) -> str:
    name = html_lib.unescape(html_lib.unescape(str(name)))
    name = re.split(r"\s+[|·]\s+", name)[0]          # drop " | Site Name"
    return re.sub(r"\s+", " ", name).strip()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _types(node: dict) -> set[str]:
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t}


def _offer_from(name, offer_node, currency_default="PHP") -> Offer | None:
    if not name or not isinstance(offer_node, dict):
        return None
    low = _to_decimal(offer_node.get("price")) or _to_decimal(offer_node.get("lowPrice"))
    high = _to_decimal(offer_node.get("highPrice"))
    if low is None:
        return None
    if high is not None and high <= low:
        high = None
    currency = str(offer_node.get("priceCurrency") or currency_default).upper()
    return Offer(_clean_name(name), low, high, currency)


def _from_jsonld(soup: BeautifulSoup, page_url: str) -> list[Offer]:
    found: dict[str, Offer] = {}
    page_host = _host(page_url)

    def add(offer: Offer | None):
        if offer and offer.raw_name.lower() not in found:
            found[offer.raw_name.lower()] = offer

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        types = _types(node)
        # Skip listings that point at another site (affiliate links to marketplaces).
        url = node.get("url")
        if isinstance(url, str) and url.startswith("http") and _host(url) != page_host:
            return
        if types & _PRODUCT_TYPES and "offers" in node:
            offers = node["offers"]
            for o in offers if isinstance(offers, list) else [offers]:
                add(_offer_from(node.get("name"), o))
        elif "Offer" in types and node.get("name"):
            add(_offer_from(node.get("name"), node))
        for value in node.values():
            walk(value)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(script.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return list(found.values())


def _from_per_person_text(soup: BeautifulSoup) -> list[Offer]:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    heading = soup.find("h1")
    name = heading.get_text(" ", strip=True) if heading else ""
    if not name and soup.title and soup.title.string:
        name = re.split(r"\s+[-|–]\s+", soup.title.string.strip())[0]
    if not name:
        return []

    prices: list[Decimal] = []
    for block in soup.find_all(["li", "p", "tr"]):
        text = block.get_text(" ", strip=True)
        if len(text) > 300 or not _PER_PERSON.search(text):
            continue
        for match in _PESO.finditer(text):
            amount = _to_decimal(match.group(0).lstrip("₱PHPphp "))
            if amount:
                prices.append(amount)
    if not prices:
        return []
    low, high = min(prices), max(prices)
    return [Offer(_clean_name(name), low, high if high > low else None, "PHP")]
