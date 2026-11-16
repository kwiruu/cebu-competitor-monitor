from decimal import Decimal

from monitor.parsers import parse_offers

URL = "https://www.example-tours.ph/package/x/"


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def ld(json_text: str) -> str:
    return f'<script type="application/ld+json">{json_text}</script>'


def test_jsonld_product_with_single_price():
    html = page("", ld('{"@type":"Product","name":"Whale Shark Day Tour | Example Tours",'
                       '"offers":{"@type":"Offer","price":"2900","priceCurrency":"PHP"}}'))
    [offer] = parse_offers(html, URL)
    assert offer.raw_name == "Whale Shark Day Tour"
    assert offer.price == Decimal("2900")
    assert offer.price_high is None
    assert offer.currency == "PHP"


def test_jsonld_aggregate_offer_keeps_low_and_high():
    html = page("", ld('{"@graph":[{"@type":"Product","name":"Mactan Island Hopping",'
                       '"offers":{"@type":"AggregateOffer","lowPrice":2112,"highPrice":7550,"priceCurrency":"PHP"}}]}'))
    [offer] = parse_offers(html, URL)
    assert (offer.price, offer.price_high) == (Decimal("2112"), Decimal("7550"))


def test_jsonld_catalog_lists_each_offer_once():
    html = page("", ld('{"@type":"OfferCatalog","itemListElement":['
                       '{"@type":"Offer","name":"Full Course Canyoneering","price":"2100","priceCurrency":"PHP"},'
                       '{"@type":"Offer","name":"Private Group","itemOffered":{"@type":"Service"}},'
                       '{"@type":"Offer","name":"Combo","price":"4500","priceCurrency":"PHP"}]}')
                + ld('{"@type":"TouristTrip","name":"Full Course Canyoneering",'
                     '"offers":{"@type":"Offer","price":"2100","priceCurrency":"PHP"}}'))
    offers = parse_offers(html, URL)
    assert [(o.raw_name, o.price) for o in offers] == [
        ("Full Course Canyoneering", Decimal("2100")),
        ("Combo", Decimal("4500")),
    ]


def test_jsonld_skips_listings_from_other_sites_and_bad_prices():
    html = page("", ld('[{"@type":"Product","name":"Own page","offers":{"@type":"AggregateOffer","lowPrice":"From USD $119"}},'
                       '{"@type":"Product","name":"Marketplace tour","url":"https://www.marketplace.com/t1",'
                       '"offers":{"@type":"Offer","price":110.17,"priceCurrency":"EUR"}}]'))
    assert parse_offers(html, URL) == []


def test_per_person_text_uses_heading_and_price_range():
    html = page("""
        <h1>Island Hopping Joiner Tour</h1>
        <ul><li>2 guests: ₱5,050 per person</li><li>3–6 guests: ₱4,500 per person</li>
            <li>7–10 guests and up: ₱4,200 per person</li></ul>
        <p>Optional zipline fee Php 600 paid on site</p>""")
    [offer] = parse_offers(html, URL)
    assert offer.raw_name == "Island Hopping Joiner Tour"
    assert (offer.price, offer.price_high) == (Decimal("4200"), Decimal("5050"))


def test_per_person_text_falls_back_to_title_and_reads_decimals():
    html = page("<p>Php 6,900.00/pax (2-4pax) for Locals; Php 7,400.00 for Foreigners</p>"
                "<p>Php 5,300.00/pax (5-10pax) for Locals; Php 5,800.00 for Foreigners</p>",
                "<title>Whaleshark and Canyoneering Tour - Local Guide</title>")
    [offer] = parse_offers(html, URL)
    assert offer.raw_name == "Whaleshark and Canyoneering Tour"
    assert (offer.price, offer.price_high) == (Decimal("5300.00"), Decimal("7400.00"))


def test_page_without_prices_returns_nothing():
    assert parse_offers(page("<h1>About us</h1><p>We love Cebu.</p>"), URL) == []


def test_broken_jsonld_does_not_crash():
    html = page("<h1>Tour</h1><p>₱1,500 per person</p>", ld("{not json"))
    [offer] = parse_offers(html, URL)
    assert offer.price == Decimal("1500")
