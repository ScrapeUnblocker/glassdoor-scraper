"""Shared fixtures: a fake ScrapeUnblocker client, so no test spends API credit."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from glassdoor_scraper import GlassdoorScraper


class UpstreamOutageError(Exception):
    """Stands in for the SDK's transient error."""


class TargetNotFoundError(Exception):
    """Stands in for the SDK's 404 error."""


class StepFailedError(Exception):
    """Stands in for the SDK's browser-step error (it carries the page HTML)."""

    def __init__(self, message: str, html: str | None = None) -> None:
        super().__init__(message)
        self.html = html


Response = Any  # an HTML string, an exception, or a callable(url, options) -> either


class FakeClient:
    """Answers ``get_page_source`` from a list of ``(url fragment, response)`` rules."""

    def __init__(self, rules: list[tuple[str, Response]] | None = None) -> None:
        self.rules = list(rules or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def add(self, fragment: str, response: Response) -> FakeClient:
        self.rules.append((fragment, response))
        return self

    def get_page_source(self, url: str, **options: Any) -> str:
        self.calls.append((url, options))
        for fragment, response in self.rules:
            if fragment in url:
                if callable(response) and not isinstance(response, type):
                    response = response(url, options)
                if isinstance(response, BaseException):
                    raise response
                return response
        raise AssertionError(f"unexpected request: {url}")


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def make_scraper() -> Callable[..., GlassdoorScraper]:
    def make(client: FakeClient, **options: Any) -> GlassdoorScraper:
        options.setdefault("transient_errors", (UpstreamOutageError,))
        options.setdefault("sleep", lambda seconds: None)
        options.setdefault("retries", 2)
        return GlassdoorScraper(client=client, **options)

    return make
