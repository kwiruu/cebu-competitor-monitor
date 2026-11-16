"""Polite page fetcher: obeys robots.txt, waits between requests, names itself."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = os.getenv("BOT_USER_AGENT", "CebuCompetitorMonitor/0.1 (price monitor; daily; respects robots.txt)")
MIN_DELAY_S = 1.0


@dataclass
class FetchResult:
    url: str
    ok: bool
    http_status: int | None = None
    html: str = ""
    error: str | None = None


class PoliteFetcher:
    def __init__(self, sleep=time.sleep, clock=time.monotonic):
        self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}
        self._sleep, self._clock = sleep, clock

    def close(self):
        self._client.close()

    def _wait(self, host: str, delay: float):
        last = self._last_request.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlparse(url)
        host = parts.netloc
        if host not in self._robots:
            parser = RobotFileParser()
            try:
                self._wait(host, MIN_DELAY_S)
                r = self._client.get(f"{parts.scheme}://{host}/robots.txt")
                # 4xx means "no robots.txt", which allows everything. 5xx: be safe, skip the site.
                if r.status_code >= 500:
                    parser = None
                else:
                    parser.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                parser = None
            self._robots[host] = parser
        return self._robots[host]

    def get(self, url: str, min_delay_s: float = MIN_DELAY_S) -> FetchResult:
        robots = self._robots_for(url)
        if robots is None:
            return FetchResult(url, False, error="robots.txt could not be read")
        if not robots.can_fetch(USER_AGENT, url):
            return FetchResult(url, False, error="blocked by robots.txt")
        delay = max(MIN_DELAY_S, float(min_delay_s), float(robots.crawl_delay(USER_AGENT) or 0))
        self._wait(urlparse(url).netloc, delay)
        try:
            r = self._client.get(url)
        except httpx.HTTPError as e:
            return FetchResult(url, False, error=type(e).__name__)
        if r.status_code != 200:
            return FetchResult(url, False, r.status_code, error=f"HTTP {r.status_code}")
        return FetchResult(url, True, 200, r.text)
