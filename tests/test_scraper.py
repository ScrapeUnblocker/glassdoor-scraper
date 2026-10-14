from __future__ import annotations

import datetime as dt

import pytest

from glassdoor_scraper import GlassdoorScraper, JobFilters, load_more_steps, unique_jobs
from glassdoor_scraper.models import Location
from glassdoor_scraper.parsing import GlassdoorNotFoundError, GlassdoorParseError
from glassdoor_scraper.scraper import (
    CLOSE_DIALOG,
    LOAD_MORE,
    MAX_PAGES,
    best_location,
    parse_location_ref,
)

from . import pages
from .conftest import FakeClient, StepFailedError, TargetNotFoundError, UpstreamOutageError


def test_search_resolves_the_location_and_applies_filters(fake_client, make_scraper) -> None:
    fake_client.add("/autocomplete/location", pages.LOCATIONS)
    fake_client.add("/Job/", pages.search_page())
    scraper = make_scraper(fake_client, today=lambda: dt.date(2026, 10, 14))
    page = scraper.search_jobs("python developer", "Austin", filters=JobFilters(days=7))
    (lookup, _), (url, options) = fake_client.calls
    assert "term=Austin" in lookup
    assert url == (
        "https://www.glassdoor.com/Job/austin-tx-python-developer-jobs-"
        "SRCH_IL.0,9_IC1139761_KO10,26.htm?fromAge=7"
    )
    assert options == {"proxy_country": "us"}  # one plain request: no browser steps
    assert page.location == "Austin, TX"
    assert page.jobs[0].posted_date == "2026-10-11"


def test_search_by_location_reference_skips_the_lookup(fake_client, make_scraper) -> None:
    fake_client.add("/Job/", pages.search_page())
    page = make_scraper(fake_client).search_jobs(None, "S:1347")
    ((url, _),) = fake_client.calls
    assert "_IS1347.htm" in url
    assert page.location == "New York, NY"  # read from the page title


def test_unknown_location(fake_client, make_scraper) -> None:
    fake_client.add("/autocomplete/location", "[]")
    with pytest.raises(GlassdoorNotFoundError):
        make_scraper(fake_client).search_jobs("nurse", "Atlantis")


def test_more_pages_click_show_more_jobs(fake_client, make_scraper) -> None:
    fake_client.add("/Job/", pages.search_page())
    make_scraper(fake_client).search_jobs("nurse", pages=3)
    ((_, options),) = fake_client.calls
    assert options["steps"] == load_more_steps(3)


def test_a_failed_step_still_returns_the_jobs_loaded_so_far(fake_client, make_scraper) -> None:
    partial = pages.search_page(total=500, cards="<ul>" + pages.job_card(1003, "SRE") + "</ul>")
    fake_client.add("/Job/", StepFailedError("step 4 timed out", html=partial))
    page = make_scraper(fake_client).search_jobs("nurse", pages=5)
    assert [job.listing_id for job in page.jobs] == [1003, 1001, 1002]
    assert not page.complete
    assert len(fake_client.calls) == 1  # not retried: steps are not idempotent


def test_step_failure_without_html_is_raised(fake_client, make_scraper) -> None:
    fake_client.add("/Job/", StepFailedError("boom"))
    with pytest.raises(StepFailedError):
        make_scraper(fake_client).search_jobs("nurse", pages=2)


def test_pages_out_of_range(fake_client, make_scraper) -> None:
    with pytest.raises(ValueError):
        make_scraper(fake_client).search_jobs("nurse", pages=MAX_PAGES + 1)


@pytest.mark.parametrize("pages_wanted", range(2, MAX_PAGES + 1))
def test_load_more_steps_fit_the_step_limit(pages_wanted: int) -> None:
    steps = load_more_steps(pages_wanted)
    assert len(steps) <= 10
    clicks = [s for s in steps if s["action"] == "click" and s["selector"] == LOAD_MORE]
    assert len(clicks) == pages_wanted - 1
    assert steps[0]["action"] == "wait_for" and steps[-1]["action"] == "wait"
    closes = [s for s in steps if s.get("selector") == CLOSE_DIALOG]
    assert len(closes) == (1 if pages_wanted >= 3 else 0)


def test_load_more_steps_range() -> None:
    for bad in (1, MAX_PAGES + 1):
        with pytest.raises(ValueError):
            load_more_steps(bad)


def test_transient_errors_are_retried_with_backoff(fake_client, make_scraper) -> None:
    answers = [UpstreamOutageError("busy"), UpstreamOutageError("busy"), pages.job_page()]
    fake_client.add("/job-listing/", lambda url, options: answers.pop(0))
    sleeps, retries = [], []
    scraper = make_scraper(
        fake_client,
        sleep=sleeps.append,
        backoff=2,
        on_retry=lambda attempt, delay, error: retries.append(attempt),
    )
    job = scraper.job("https://www.glassdoor.com/job-listing/x-JV.htm?jl=1010288405565")
    assert job.listing_id == 1010288405565
    assert (
        fake_client.calls[0][0] == "https://www.glassdoor.com/job-listing/JV.htm?jl=1010288405565"
    )
    assert sleeps == [2, 4] and retries == [1, 2]


def test_pages_without_data_are_retried_then_raised(fake_client, make_scraper) -> None:
    fake_client.add("/job-listing/", "<html><title>Just a moment</title></html>")
    with pytest.raises(GlassdoorParseError):
        make_scraper(fake_client, retries=1).job(1)
    assert len(fake_client.calls) == 2


def test_not_found_is_not_retried(fake_client, make_scraper) -> None:
    fake_client.add("/job-listing/", TargetNotFoundError("404"))
    with pytest.raises(GlassdoorNotFoundError):
        make_scraper(fake_client).job(1)
    assert len(fake_client.calls) == 1


def test_company_by_name_then_salaries_reuse_the_profile(fake_client, make_scraper) -> None:
    fake_client.add("/Search/results.htm", pages.company_search_page())
    fake_client.add("/Overview/", pages.company_page())
    fake_client.add("/Salary/Acme-Salaries-E123_P2.htm", pages.salaries_page(page=2))
    fake_client.add("/Salary/Acme-Salaries-E123.htm", pages.salaries_page(page=1))
    scraper = make_scraper(fake_client)
    company = scraper.company("Acme")
    assert company.id == 123 and company.name == "Acme"
    result = list(scraper.iter_salaries("Acme", pages=5))
    assert [page.page for page in result] == [1, 2]  # stops at the last page
    urls = [url for url, _ in fake_client.calls]
    assert urls[1].endswith("/Overview/Working-at-Company-EI_IE123.11,18.htm")
    assert sum("/Overview/" in url for url in urls) == 1  # salary slug came from the profile


def test_salaries_from_a_salary_url_need_no_profile(fake_client, make_scraper) -> None:
    fake_client.add("/Salary/", pages.salaries_page())
    page = make_scraper(fake_client).salaries(
        "https://www.glassdoor.com/Salary/Acme-Salaries-E123.htm", job_title="Engineer"
    )
    assert page.salaries[0].job_title == "Senior Consultant 1"
    ((url, _),) = fake_client.calls
    assert url.endswith("/Salary/Acme-Salaries-E123.htm?filter.jobTitleFTS=Engineer")


def test_unknown_company_name(fake_client, make_scraper) -> None:
    fake_client.add("/Search/results.htm", "<html><body>no results</body></html>")
    with pytest.raises(GlassdoorNotFoundError):
        make_scraper(fake_client).company("Nonexistent Company Inc")


def test_iter_searches_reports_failures_and_unique_jobs_dedupes(fake_client, make_scraper) -> None:
    fake_client.add("/nurse-jobs", TargetNotFoundError("404"))
    fake_client.add("/Job/", pages.search_page())
    errors = []
    results = list(
        make_scraper(fake_client).iter_searches(
            ["python", "nurse", "java"],
            on_error=lambda keyword, place, error: errors.append(keyword),
        )
    )
    assert len(results) == 2 and errors == ["nurse"]
    assert [job.listing_id for job in unique_jobs(results)] == [1001, 1002]


def test_location_refs() -> None:
    assert parse_location_ref("C:1132348") == Location(1132348, "C", "C:1132348")
    assert parse_location_ref("ic1132348").id == 1132348
    assert parse_location_ref("N2").type == "N"
    assert parse_location_ref("Cairo") is None
    assert parse_location_ref("New York, NY") is None


def test_default_client_reads_the_key_from_the_environment(monkeypatch) -> None:
    pytest.importorskip("scrapeunblocker")
    monkeypatch.setenv("SCRAPEUNBLOCKER_KEY", "test-key-not-real")
    scraper = GlassdoorScraper()
    assert scraper.country == "us"


def test_fake_client_rejects_unexpected_requests() -> None:
    with pytest.raises(AssertionError):
        FakeClient().get_page_source("https://example.com")


def _place(location_id: int, name: str, long_name: str, city: str, state: str, code: str):
    country = {"US": "United States", "CA": "Canada", "GB": "United Kingdom"}[code]
    return Location(location_id, "C", name, long_name, city, state, country, code)


TORONTOS = [
    _place(1146311, "Toronto, OH", "Toronto, OH (US)", "Toronto", "Ohio", "US"),
    _place(2281069, "Toronto, ON", "Toronto, ON (Canada)", "Toronto", "Ontario", "CA"),
]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Toronto, ON", 2281069),  # exact name, though Glassdoor lists it second
        ("toronto ontario", 1146311),  # no comma parts to compare: Glassdoor's order
        ("Toronto, Ontario", 2281069),
        ("Toronto, Canada", 2281069),
        ("Toronto", 1146311),
    ],
)
def test_best_location(term: str, expected: int) -> None:
    assert best_location(term, TORONTOS).id == expected


def test_best_location_uses_the_country_in_brackets() -> None:
    london = [
        _place(1, "Londonderry, NH", "Londonderry, NH (US)", "Londonderry", "New Hampshire", "US"),
        _place(2671300, "London, England", "London, England (UK)", "London", "England", "GB"),
    ]
    assert best_location("London, UK", london).id == 2671300
    assert best_location("anything", []) is None
