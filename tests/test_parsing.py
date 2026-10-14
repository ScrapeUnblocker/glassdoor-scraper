from __future__ import annotations

import datetime as dt

import pytest

from glassdoor_scraper.parsing import (
    GlassdoorParseError,
    html_to_text,
    parse_company_page,
    parse_company_search,
    parse_job_cards,
    parse_job_page,
    parse_locations,
    parse_salaries_page,
    parse_salary_text,
    parse_search_page,
    posted_date,
)

from . import pages

TODAY = dt.date(2026, 10, 14)


def test_search_page_reads_the_job_payload() -> None:
    page = parse_search_page(pages.search_page(), "https://x", today=TODAY)
    assert page.total == 2
    assert page.keyword == "python developer"
    assert page.location == "New York, NY"  # from the page title
    assert page.filters == {"fromAge": "7", "remoteWorkType": "1"}  # non-default only
    assert page.pages_loaded == 1 and page.complete
    first, second = page.jobs
    assert first.listing_id == 1001
    assert first.title == "Python Developer"
    assert first.company == "Acme" and first.company_id == 123 and first.company_rating == 4.2
    assert (first.salary_min, first.salary_median, first.salary_max) == (60, 62.5, 65)
    assert first.salary_currency == "USD"
    assert first.salary_period == "hourly"
    assert first.salary_source == "employer"
    assert first.age_days == 3 and first.posted_date == "2026-10-11"
    assert first.sponsored is True and first.easy_apply is True
    assert first.skills == ["Python"]
    assert first.tags == ["401(k)", "Full-time"]
    assert first.snippet == "About Python Developer."
    assert first.location == "New York, NY" and first.location_id == 1132348
    assert first.url.endswith("jl=1001")
    # no pay -> every salary field empty; rating 0 means "not rated"
    assert second.salary_min is None and second.salary_currency is None
    assert second.company_rating is None


def test_search_page_location_override() -> None:
    page = parse_search_page(pages.search_page(), "https://x", location="New York, NY (US)")
    assert page.location == "New York, NY (US)"


def test_rendered_cards_merge_with_the_payload_in_page_order() -> None:
    cards = pages.job_card(1003, "Software Engineer") + pages.job_card(
        1001, "Python Developer", salary=None, award="Best CEO"
    )
    html = pages.search_page(total=95, cards=f"<ul>{cards}</ul>")
    page = parse_search_page(html, "https://x", pages_requested=3, today=TODAY)
    assert [job.listing_id for job in page.jobs] == [1003, 1001, 1002]
    card_only, merged, payload_only = page.jobs
    # a card-only job (loaded with "Show more jobs")
    assert card_only.title == "Software Engineer"
    assert card_only.company == "Lockheed Martin" and card_only.company_id == 404
    assert card_only.company_rating == 4.1
    assert (card_only.salary_min, card_only.salary_max) == (88000, 146000)
    assert card_only.salary_source == "estimate" and card_only.salary_currency == "USD"
    assert card_only.easy_apply is True
    assert card_only.awards == ["Best Places to Work"]
    assert card_only.skills == ["Git", "Java", "Linux"]
    assert card_only.snippet == "Build things in a team"
    assert card_only.age_days is None and card_only.sponsored is None
    assert card_only.logo == "https://media.glassdoor.com/sql/404/logo.png"
    # a payload job keeps its rich fields and gains what only the card shows
    assert merged.salary_median == 62.5 and merged.age_days == 3
    assert merged.awards == ["Best CEO"]
    assert payload_only.listing_id == 1002
    # 3 jobs can't fill the 3 pages asked for, and the total says more exist
    assert page.pages_loaded == 1 and not page.complete


def test_card_without_easy_apply_or_salary() -> None:
    html = pages.job_card(7, "Analyst", salary=None, easy_apply=False, award=None)
    (job,) = parse_job_cards(f"<ul>{html}</ul>")
    assert job.easy_apply is False
    assert job.salary_min is None and job.awards == []


def test_search_page_without_results_data_is_a_parse_error() -> None:
    with pytest.raises(GlassdoorParseError):
        parse_search_page("<html><title>Security check</title></html>", "https://x")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "$60.00 - $65.00 Per Hour (Employer provided)",
            (60.0, 65.0, "USD", "hourly", "employer"),
        ),
        ("$115K (Employer provided)", (115000.0, 115000.0, "USD", "annual", "employer")),
        (
            "£45K - £55K (Glassdoor est.)",
            (45000.0, 55000.0, "GBP", "annual", "estimate"),
        ),
        ("CA$80K - CA$95K", (80000.0, 95000.0, "CAD", "annual", None)),
        ("€3,500 - €4,000 Per Month", (3500.0, 4000.0, "EUR", "monthly", None)),
        ("$1.2M", (1200000.0, 1200000.0, "USD", "annual", None)),
    ],
)
def test_parse_salary_text(text: str, expected: tuple) -> None:
    parsed = parse_salary_text(text)
    assert (
        parsed["min"],
        parsed["max"],
        parsed["currency"],
        parsed["period"],
        parsed["source"],
    ) == expected


def test_parse_salary_text_empty() -> None:
    assert parse_salary_text(None) == dict.fromkeys(("min", "max", "currency", "period", "source"))
    assert parse_salary_text("Salary not listed")["min"] is None


def test_job_page() -> None:
    job = parse_job_page(pages.job_page(), "https://x", today=TODAY)
    assert job.listing_id == 1010288405565
    assert job.title == "Software Engineer - Early Career"
    assert job.company == "Lockheed Martin" and job.company_id == 404
    assert (job.salary_min, job.salary_median, job.salary_max) == (88189, 117176, 146163)
    assert job.salary_period == "annual" and job.salary_source == "employer"
    assert job.job_types == ["Full-time"] and job.remote == []
    assert job.education == ["Bachelor's degree"] and job.skills == ["Git", "Python"]
    assert job.posted_date == "2026-10-07"  # the page's own date wins over age_days
    assert job.region == "New York State" and job.latitude == pytest.approx(40.70028)
    assert job.description == "WHAT WE DO\nBuild – café systems\n\n- Python"
    assert job.description_html.startswith("<div><p>WHAT WE DO")
    assert job.company_revenue == "$10+ billion (USD)"  # "$$" unescaped
    assert job.company_founded == 1995 and job.company_type == "Company - Public"
    ratings = job.company_ratings
    assert ratings.overall == 4.1 and ratings.recommend_to_friend_pct == 83
    assert ratings.ceo_approval_pct == 81 and ratings.ceo_name == "Jane Doe"
    assert job.review_highlights[0].sentence == "great work life balance"
    assert job.benefits_rating == 4.1 and job.company_review_count == 2914
    assert job.sponsored is True and job.easy_apply is False and job.expired is False


def test_job_page_without_details_is_a_parse_error() -> None:
    with pytest.raises(GlassdoorParseError):
        parse_job_page(pages.flight_html({"1": {"other": True}}), "https://x")


def test_company_page() -> None:
    company = parse_company_page(pages.company_page(), "https://x/overview", 123)
    assert company.id == 123
    assert company.name == "Acme" and company.legal_name == "Acme Corporation"
    assert company.founded == 1949 and company.stock == "ACME"
    assert company.revenue == "$100 to $500 million (USD)"
    assert company.industry == "Software" and company.sector == "Information Technology"
    assert company.description == "We make anvils." and company.mission == "Anvils for all."
    assert company.office_locations == 12 and company.salary_count == 1500
    assert company.awards == ["Best Places to Work & Grow (2026)", "Top Employer"]
    ratings = company.ratings
    assert ratings.overall == 4.3 and ratings.review_count == 1052
    assert ratings.recommend_to_friend_pct == 88 and ratings.positive_outlook_pct == 81
    assert ratings.ceo_name == "Wile E. Coyote"
    assert company.industry_ratings.overall == 3.63
    assert company.rating_distribution == {
        "overall": {"1": 10, "2": 20, "3": 30, "4": 40, "5": 50},
        "compensation_benefits": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5},
        "recommend_to_friend": {"recommend": 90, "wont_recommend": 10},
    }
    assert [review.review_id for review in company.reviews] == [9001, 9002]
    first = company.reviews[0]
    assert first.date == "2026-10-12" and first.rating == 5 and first.title == "Great place"
    assert first.current_employee is True and first.years_employed == 3
    assert first.recommends == "POSITIVE" and first.ceo_opinion == "APPROVE"
    assert first.employer_response == "Thanks for the feedback."
    assert company.url == "https://www.glassdoor.com/Overview/Working-at-Acme-EI_IE123.11,15.htm"
    assert company.reviews_url == "https://www.glassdoor.com/Reviews/Acme-Reviews-E123.htm"
    assert company.salaries_url == "https://www.glassdoor.com/Salary/Acme-Salaries-E123.htm"
    assert company.jobs_url.endswith("/Jobs/Acme-Jobs-E123.htm")


def test_company_page_without_profile_is_a_parse_error() -> None:
    with pytest.raises(GlassdoorParseError):
        parse_company_page(pages.flight_html({"1": {"x": 1}}), "https://x", 123)


def test_salaries_page() -> None:
    page = parse_salaries_page(pages.salaries_page(page=2), "https://x", 123, 2)
    assert page.company == "Acme" and page.page == 2 and page.pages == 2
    assert page.job_title_count == 12 and page.location == "United States"
    (salary,) = page.salaries
    assert salary.job_title == "Senior Consultant 2" and salary.salary_count == 3038
    assert salary.currency == "USD" and salary.pay_period == "annual"
    assert (salary.base_p10, salary.base_median, salary.base_p90) == (100002, 120002, 140002)
    assert salary.total_median == 130000 and salary.last_reported == "2026-10-07"


def test_salaries_page_without_data_is_a_parse_error() -> None:
    with pytest.raises(GlassdoorParseError):
        parse_salaries_page(pages.flight_html({"1": {"x": 1}}), "https://x", 123)


def test_locations_from_bare_or_wrapped_json() -> None:
    for text in (pages.LOCATIONS, f"<html><body><pre>{pages.LOCATIONS}</pre></body></html>"):
        austin, texas = parse_locations(text)
        assert (austin.id, austin.type, austin.name) == (1139761, "C", "Austin, TX")
        assert austin.country_code == "US"
        assert (texas.id, texas.type) == (1347, "S")


def test_location_lookup_error() -> None:
    with pytest.raises(GlassdoorParseError):
        parse_locations('{"status": "INTERNAL_SERVER_ERROR", "message": "oops"}')
    with pytest.raises(GlassdoorParseError):
        parse_locations("<html>blocked</html>")


def test_company_search() -> None:
    (match,) = parse_company_search(pages.company_search_page())
    assert (match.id, match.name, match.legal_name, match.rating) == (
        123,
        "Acme",
        "Acme Corporation",
        4.3,
    )
    assert parse_company_search("<html></html>") == []


def test_helpers() -> None:
    assert posted_date(None) is None
    assert posted_date(10, TODAY) == "2026-10-04"
    assert html_to_text(None) is None
    assert html_to_text("<p>One</p><p>Two<br/>Three</p>") == "One\n\nTwo\nThree"
