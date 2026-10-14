"""Scrape Glassdoor through the ScrapeUnblocker ``getPageSource`` API.

:class:`GlassdoorScraper` builds the Glassdoor URL for each kind of page, fetches it
through ScrapeUnblocker and parses the data the page ships with. A plain request
returns the first 30 jobs of a search; for more, the scraper runs browser steps that
click "Show more jobs" (30 jobs per click, up to :data:`MAX_PAGES` pages in one
request). Timeouts, transient API errors and pages that come back without their data
are retried with doubling backoff.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Callable, TypeVar

from .models import Company, CompanyMatch, JobDetails, JobSearchPage, Location, SalaryPage
from .parsing import (
    GlassdoorNotFoundError,
    GlassdoorParseError,
    parse_company_page,
    parse_company_search,
    parse_job_page,
    parse_locations,
    parse_salaries_page,
    parse_search_page,
)
from .urls import (
    LOCATION_TYPES,
    JobFilters,
    company_search_url,
    employer_id,
    is_company_ref,
    job_url,
    location_lookup_url,
    overview_url,
    salaries_url,
    salary_path,
    search_url,
)

T = TypeVar("T")

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError", "NotFoundError")
_STEP_FAILED = "StepFailedError"

#: Jobs per search page (and per "Show more jobs" click).
PAGE_SIZE = 30
#: Pages one search can load: the first page plus four "Show more jobs" clicks fit in
#: the API's limit of 10 browser steps per request.
MAX_PAGES = 5

LOAD_MORE = '[data-test="load-more"]'
#: After the first "Show more jobs" click Glassdoor opens a sign-up dialog once.
CLOSE_DIALOG = '[data-test="auth-modal-close-button"]'


def load_more_steps(pages: int) -> list[dict[str, Any]]:
    """Browser steps that load ``pages`` pages of a search (``pages - 1`` clicks)."""
    if not 2 <= pages <= MAX_PAGES:
        raise ValueError(f"load_more_steps needs 2-{MAX_PAGES} pages, got {pages}")
    click = {"action": "click", "selector": LOAD_MORE}
    steps: list[dict[str, Any]] = [
        {"action": "wait_for", "selector": LOAD_MORE, "timeout_ms": 20000},
        {"action": "wait", "value": 3000},  # let the page finish hydrating
        click,
    ]
    if pages == 2:
        return steps + [{"action": "wait", "value": 3000}]
    steps += [{"action": "click", "selector": CLOSE_DIALOG}, click]
    for _ in range(pages - 3):
        steps += [{"action": "wait", "value": 2500}, click]
    return steps + [{"action": "wait", "value": 3000}]


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Best-effort tuple of ScrapeUnblocker exceptions worth retrying.

    Imported lazily so the package is usable (and unit-testable) even when the
    ``scrapeunblocker`` SDK is not installed.
    """
    try:
        import scrapeunblocker  # type: ignore
    except Exception:  # pragma: no cover - depends on SDK availability
        return ()
    found = (getattr(scrapeunblocker, name, None) for name in _TRANSIENT_NAMES)
    return tuple(cls for cls in found if isinstance(cls, type))


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def parse_location_ref(value: str) -> Location | None:
    """A location given directly as ``C:1132348`` / ``IC1132348`` (type + Glassdoor ID)."""
    text = value.strip().upper()
    for prefix in ("I", ""):
        for kind in LOCATION_TYPES:
            for sep in (":", ""):
                head = f"{prefix}{kind}{sep}"
                if text.startswith(head) and text[len(head) :].isdigit():
                    return Location(id=int(text[len(head) :]), type=kind, name=value.strip())
    return None


def _words(text: str | None) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", (text or "").lower()).split())


def best_location(term: str, matches: Sequence[Location]) -> Location | None:
    """The lookup result that best fits what was typed.

    Glassdoor's lookup ranks by popularity, so "Toronto, ON" lists Toronto, OH first.
    An exact name wins; otherwise the match whose city, state or country parts agree
    with the most comma-separated parts of ``term``; ties keep Glassdoor's order.
    """
    wanted = [_words(part) for part in term.split(",") if _words(part)]
    if not matches or not wanted:
        return matches[0] if matches else None

    def score(location: Location) -> int:
        if _words(location.name) == _words(term) or _words(location.long_name) == _words(term):
            return 100
        parts = {_words(part) for part in location.name.split(",")}
        parts |= {
            _words(value)
            for value in (location.city, location.state, location.country, location.country_code)
            if value
        }
        extra = re.search(r"\(([^)]+)\)", location.long_name or "")
        if extra:
            parts.add(_words(extra.group(1)))
        head = 2 if wanted[0] in (_words(location.city), _words(location.name.split(",")[0])) else 0
        return head + sum(1 for part in wanted[1:] if part in parts)

    return max(matches, key=score)  # max keeps the first of equal scores


class GlassdoorScraper:
    """Search Glassdoor jobs and read job pages, company profiles and salaries.

    Args:
        api_key: ScrapeUnblocker key. If omitted, the SDK reads
            ``SCRAPEUNBLOCKER_KEY`` from the environment.
        client: A pre-built client (or any object exposing
            ``get_page_source(url, proxy_country=..., steps=...)``). Mainly for testing.
        country: Country to route requests through (default ``us``). Glassdoor serves
            every location from glassdoor.com, so this rarely needs changing.
        retries: Extra attempts per request on transient failures.
        backoff: Seconds before the first retry; doubles on every further retry.
        max_backoff: Upper bound for a single wait between retries.
        timeout: Per-request timeout passed to the SDK client.
        transient_errors: Exception classes treated as retryable. Defaults to
            the ScrapeUnblocker transient set.
        on_retry: Optional callback ``(attempt, delay_seconds, error)`` invoked
            before every retry (handy for progress output).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        country: str | None = "us",
        retries: int = 3,
        backoff: float = 5.0,
        max_backoff: float = 60.0,
        timeout: float = 180.0,
        transient_errors: Sequence[type[BaseException]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, float, BaseException], None] | None = None,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        if client is None:
            from scrapeunblocker import Client  # local import: optional dep

            client = Client(api_key=api_key, timeout=timeout)
        self._client = client
        self.country = (country or "").strip().lower() or None
        self.retries = max(0, int(retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self.on_retry = on_retry
        transient = tuple(transient_errors) if transient_errors is not None else _transient_errors()
        self._transient = (*transient, GlassdoorParseError)
        self._sleep = sleep
        self._today = today
        self._salary_slugs: dict[int, str] = {}

    # ------------------------------------------------------------------ #
    # Fetching
    # ------------------------------------------------------------------ #

    def _retry(self, action: Callable[[], T]) -> T:
        """Run ``action``, retrying transient failures with doubling backoff."""
        attempt = 0
        while True:
            try:
                return action()
            except Exception as exc:
                if not isinstance(exc, self._transient) or attempt >= self.retries:
                    raise
                attempt += 1
                delay = min(self.backoff * 2 ** (attempt - 1), self.max_backoff)
                if self.on_retry is not None:
                    self.on_retry(attempt, delay, exc)
                self._sleep(delay)

    def fetch(self, url: str, steps: list[dict[str, Any]] | None = None) -> str:
        """One getPageSource call: the HTML of a Glassdoor page.

        A page Glassdoor answers with 404 raises :class:`GlassdoorNotFoundError`.
        If a browser step fails (say "Show more jobs" is gone because every job is
        already on the page) the page as it was at that moment is returned.
        """
        options: dict[str, Any] = {}
        if self.country:
            options["proxy_country"] = self.country
        if steps:
            options["steps"] = steps
        try:
            html = self._client.get_page_source(url, **options)
        except Exception as exc:
            if _is_named(exc, *_NOT_FOUND_NAMES):
                raise GlassdoorNotFoundError(f"Glassdoor has no page at {url}") from exc
            partial = getattr(exc, "html", None)
            if steps and _is_named(exc, _STEP_FAILED) and isinstance(partial, str) and partial:
                return partial
            raise
        return html if isinstance(html, str) else ""

    # ------------------------------------------------------------------ #
    # Locations
    # ------------------------------------------------------------------ #

    def locations(self, term: str) -> list[Location]:
        """Glassdoor locations (cities, states, countries) matching ``term``."""
        if not term.strip():
            raise ValueError("give a location to look up, e.g. 'Austin, TX'")
        url = location_lookup_url(term)
        return self._retry(lambda: parse_locations(self.fetch(url)))

    def resolve_location(self, location: str | Location | None) -> Location | None:
        """A :class:`Location` for a name ("Austin, TX"), a ``C:1139761`` reference or
        a ``Location``. A name resolves to the lookup result that fits it best."""
        if location is None or isinstance(location, Location):
            return location
        direct = parse_location_ref(location)
        if direct is not None:
            return direct
        match = best_location(location, self.locations(location))
        if match is None:
            raise GlassdoorNotFoundError(f"Glassdoor knows no location called {location!r}")
        return match

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #

    def search_jobs(
        self,
        keyword: str | None = None,
        location: str | Location | None = None,
        *,
        filters: JobFilters | None = None,
        pages: int = 1,
    ) -> JobSearchPage:
        """Search jobs by keyword and/or location.

        ``pages=1`` is one fast request with the richest data (30 jobs). ``pages`` 2-5
        clicks "Show more jobs" in a real browser and returns up to ``30 * pages`` jobs.
        """
        if not 1 <= pages <= MAX_PAGES:
            raise ValueError(f"pages must be between 1 and {MAX_PAGES}")
        place = self.resolve_location(location)
        url = search_url(
            keyword,
            place.id if place else None,
            place.type if place else "C",
            filters,
            place.name if place else None,
        )
        steps = load_more_steps(pages) if pages > 1 else None
        by_id = isinstance(location, str) and parse_location_ref(location) is not None
        label = place.name if place and not by_id else None  # else read from the page

        def attempt() -> JobSearchPage:
            html = self.fetch(url, steps)
            return parse_search_page(
                html, url, pages_requested=pages, location=label, today=self._today()
            )

        return self._retry(attempt)

    def iter_searches(
        self,
        keywords: Iterable[str | None],
        locations: Iterable[str | Location | None] = (None,),
        *,
        filters: JobFilters | None = None,
        pages: int = 1,
        on_error: Callable[[str | None, Any, Exception], None] | None = None,
    ) -> Iterator[JobSearchPage]:
        """Run a search for every keyword x location pair (dedupe across them yourself,
        or use :func:`unique_jobs`). Failures go to ``on_error`` when given."""
        places = list(locations) or [None]
        for keyword in keywords:
            for place in places:
                try:
                    yield self.search_jobs(keyword, place, filters=filters, pages=pages)
                except Exception as exc:
                    if on_error is None:
                        raise
                    on_error(keyword, place, exc)

    def job(self, listing: int | str) -> JobDetails:
        """Full details of a job, by listing ID or job URL."""
        url = job_url(listing)
        return self._retry(lambda: parse_job_page(self.fetch(url), url, today=self._today()))

    # ------------------------------------------------------------------ #
    # Companies
    # ------------------------------------------------------------------ #

    def find_companies(self, name: str) -> list[CompanyMatch]:
        """Companies matching a name (Glassdoor's best match first)."""
        if not name.strip():
            raise ValueError("give a company name to look up")
        url = company_search_url(name)
        return self._retry(lambda: parse_company_search(self.fetch(url)))

    def company_id(self, company: int | str) -> int:
        """A company ID from an ID, a company URL or a company name."""
        if is_company_ref(company):
            return employer_id(company)
        matches = self.find_companies(str(company))
        if not matches:
            raise GlassdoorNotFoundError(f"Glassdoor found no company called {company!r}")
        return matches[0].id

    def company(self, company: int | str) -> Company:
        """A company profile by ID, company URL or name: details, ratings (with the
        industry benchmark), star distribution and the reviews on the company page."""
        number = self.company_id(company)
        url = overview_url(number)
        profile = self._retry(lambda: parse_company_page(self.fetch(url), url, number))
        path = salary_path(profile.salaries_url or "")
        if path:
            self._salary_slugs[number] = path[0]
        return profile

    def _salary_slug(self, company: int | str) -> tuple[str, int]:
        if isinstance(company, str):
            path = salary_path(company)
            if path:
                return path
        number = self.company_id(company)
        if number not in self._salary_slugs:
            profile = self.company(number)
            if number not in self._salary_slugs:
                raise GlassdoorNotFoundError(
                    f"no salaries page for company {profile.name or number}"
                )
        return self._salary_slugs[number], number

    def salaries(
        self,
        company: int | str,
        *,
        page: int = 1,
        job_title: str | None = None,
    ) -> SalaryPage:
        """One page (up to 10 job titles) of a company's salaries.

        ``job_title`` keeps only that job title (Glassdoor matches it to its own
        title names, e.g. "Software Engineer").
        """
        slug, number = self._salary_slug(company)
        url = salaries_url(slug, number, page, job_title)
        return self._retry(lambda: parse_salaries_page(self.fetch(url), url, number, page))

    def iter_salaries(
        self,
        company: int | str,
        *,
        pages: int = 1,
        start_page: int = 1,
        job_title: str | None = None,
    ) -> Iterator[SalaryPage]:
        """Salary pages ``start_page`` .. ``start_page + pages - 1`` (stops at the last page)."""
        number = start_page
        while number < start_page + pages:
            result = self.salaries(company, page=number, job_title=job_title)
            yield result
            if not result.salaries or (result.pages is not None and number >= result.pages):
                return
            number += 1


def unique_jobs(pages: Iterable[JobSearchPage]) -> list[Any]:
    """All jobs of several searches, each listing once (first occurrence wins)."""
    seen: set[int] = set()
    jobs = []
    for page in pages:
        for job in page.jobs:
            if job.listing_id not in seen:
                seen.add(job.listing_id)
                jobs.append(job)
    return jobs
