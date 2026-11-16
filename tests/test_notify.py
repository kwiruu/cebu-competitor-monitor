from decimal import Decimal

import httpx

from monitor import notify


def change(**overrides):
    base = dict(id=7, competitor="Alpha Tours", is_us=False, offer="Island Hopping", category="island_hopping",
                change_type="price_change", old_value=Decimal("3000"), new_value=Decimal("2600"),
                pct_change=Decimal("-13.33"), detected_at=None)
    return {**base, **overrides}


def test_big_price_move_is_high_small_is_low():
    assert notify.severity(change(), 10) == "high"
    assert notify.severity(change(pct_change=Decimal("4.00")), 10) == "low"
    assert notify.severity(change(pct_change=Decimal("10.00")), 10) == "high"


def test_new_and_removed_offers_are_always_high():
    assert notify.severity(change(change_type="new_offer", pct_change=None), 10) == "high"
    assert notify.severity(change(change_type="removed_offer", pct_change=None), 10) == "high"


def test_messages_read_as_plain_sentences():
    assert notify.message(change(), {}) == (
        'Alpha Tours lowered "Island Hopping" from PHP 3,000 to PHP 2,600 (-13.3%).')
    raised = change(old_value=Decimal("2600"), new_value=Decimal("3000"), pct_change=Decimal("15.38"))
    assert "raised" in notify.message(raised, {}) and "(+15.4%)" in notify.message(raised, {})
    new = change(change_type="new_offer", old_value=None, new_value=Decimal("2100"), pct_change=None)
    assert notify.message(new, {}) == 'Alpha Tours added a new package: "Island Hopping" at PHP 2,100.'
    gone = change(change_type="removed_offer", new_value=None, pct_change=None)
    assert notify.message(gone, {}) == 'Alpha Tours removed "Island Hopping" (was PHP 3,000).'


def test_message_compares_with_our_own_price_when_we_have_one():
    text = notify.message(change(), {"island_hopping": Decimal("3250")})
    assert text.endswith("That is 20% cheaper than our cheapest in this category (PHP 3,250).")
    assert "our cheapest" not in notify.message(change(), {"canyoneering": Decimal("2000")})
    assert "our cheapest" not in notify.message(change(is_us=True), {"island_hopping": Decimal("3250")})


def test_payload_shape():
    failed = [{"competitor": "Beta", "url": "https://b.test/x", "error": "HTTP 500"}]
    payload = notify.build_payload(3, "partial", [change()], failed, {}, threshold_pct=10)
    assert payload["run_id"] == 3 and payload["run_status"] == "partial" and payload["failed_pages"] == failed
    [item] = payload["changes"]
    assert item["change_id"] == 7 and item["severity"] == "high" and item["status"] == "new"
    assert item["old_value"] == 3000.0 and item["pct_change"] == -13.33


def client_answering(*statuses):
    calls = []

    def handler(request):
        calls.append(request)
        status = statuses[min(len(calls), len(statuses)) - 1]
        if status is None:
            raise httpx.ConnectError("asleep")
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_send_retries_while_n8n_wakes_up_and_sends_the_secret():
    client, calls = client_answering(None, 502, 200)
    waits = []
    assert notify.send("https://n8n.test/webhook/x", {"a": 1}, "s3cret", client, waits.append) is True
    assert len(calls) == 3 and waits == [5, 15]
    assert calls[0].headers["X-Monitor-Secret"] == "s3cret"


def test_send_gives_up_after_all_retries():
    client, calls = client_answering(503)
    assert notify.send("https://n8n.test/webhook/x", {}, "", client, lambda s: None) is False
    assert len(calls) == 4


def test_send_does_not_retry_a_rejected_request():
    client, calls = client_answering(403)
    assert notify.send("https://n8n.test/webhook/x", {}, "wrong", client, lambda s: None) is False
    assert len(calls) == 1
