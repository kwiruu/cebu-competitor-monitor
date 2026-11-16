import httpx

from monitor.fetch import PoliteFetcher


def make_fetcher(handler):
    waits = []
    now = [0.0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    fetcher = PoliteFetcher(sleep=sleep, clock=lambda: now[0])
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    return fetcher, waits


def test_blocked_by_robots_is_not_fetched():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/")
        return httpx.Response(200, text="<html></html>")

    fetcher, _ = make_fetcher(handler)
    result = fetcher.get("https://site.test/private/page")
    assert not result.ok and result.error == "blocked by robots.txt"
    assert seen == ["/robots.txt"]


def test_waits_for_crawl_delay_between_requests():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 20")
        return httpx.Response(200, text="<html></html>")

    fetcher, waits = make_fetcher(handler)
    assert fetcher.get("https://site.test/a").ok
    assert fetcher.get("https://site.test/b").ok
    assert waits == [20.0, 20.0]      # after robots.txt, and between the two pages


def test_missing_robots_allows_and_error_page_is_reported():
    def handler(request):
        return httpx.Response(404 if request.url.path != "/gone" else 500, text="")

    fetcher, _ = make_fetcher(handler)
    result = fetcher.get("https://site.test/gone")
    assert not result.ok and result.http_status == 500
