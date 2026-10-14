from __future__ import annotations

import pytest

from glassdoor_scraper.urls import (
    JobFilters,
    company_search_url,
    employer_id,
    is_company_ref,
    job_url,
    keyword_slug,
    listing_id,
    location_lookup_url,
    location_slug,
    overview_url,
    salaries_url,
    salary_path,
    search_url,
)


def test_search_url_with_keyword_and_city() -> None:
    url = search_url("data analyst", 1139761, "C", JobFilters(days=7), "Austin, TX")
    assert url == (
        "https://www.glassdoor.com/Job/austin-tx-data-analyst-jobs-"
        "SRCH_IL.0,9_IC1139761_KO10,22.htm?fromAge=7"
    )


def test_search_url_keeps_symbols_in_the_keyword() -> None:
    url = search_url("C++  Developer", 1132348, "C", None, "New York, NY")
    assert url == (
        "https://www.glassdoor.com/Job/new-york-ny-c%2B%2B-developer-jobs-"
        "SRCH_IL.0,11_IC1132348_KO12,25.htm"
    )


def test_search_url_keyword_only_location_only_and_country() -> None:
    assert search_url("python developer") == (
        "https://www.glassdoor.com/Job/python-developer-jobs-SRCH_KO0,16.htm"
    )
    assert search_url(None, 1347, "S", None, "Texas") == (
        "https://www.glassdoor.com/Job/texas-jobs-SRCH_IL.0,5_IS1347.htm"
    )
    assert search_url("nurse", 2, "N", None, "United Kingdom").endswith(
        "united-kingdom-nurse-jobs-SRCH_IL.0,14_IN2_KO15,20.htm"
    )


def test_search_url_needs_a_keyword_or_location() -> None:
    with pytest.raises(ValueError):
        search_url("  ")
    with pytest.raises(ValueError):
        search_url("x", 1, "Z")


def test_slugs() -> None:
    assert location_slug("New York, NY") == "new-york-ny"
    assert location_slug(None) == "location"
    assert keyword_slug("UI/UX  Designer") == "ui-ux-designer"


def test_all_filters_become_query_parameters() -> None:
    filters = JobFilters(
        days=3,
        sort="newest",
        min_salary=120000,
        max_salary=200000,
        min_rating=4,
        remote=True,
        easy_apply=True,
        seniority="mid-senior",
        company_size="5001+",
        job_type="full-time",
        radius=10,
        company_id=3803,
    )
    assert filters.params() == [
        ("fromAge", "3"),
        ("sortBy", "date_desc"),
        ("minSalary", "120000"),
        ("maxSalary", "200000"),
        ("minRating", "4.0"),
        ("remoteWorkType", "1"),
        ("applicationType", "1"),
        ("seniorityType", "midseniorlevel"),
        ("employerSizes", "5"),
        ("jobTypeIndeed", "CF3CP"),
        ("radius", "10"),
        ("companyId", "3803"),
    ]
    assert JobFilters(sort="relevant").params() == []


@pytest.mark.parametrize(
    "filters",
    [
        JobFilters(days=5),
        JobFilters(sort="oldest"),
        JobFilters(min_salary=-1),
        JobFilters(min_salary=100, max_salary=50),
        JobFilters(min_rating=5),
        JobFilters(seniority="intern"),
        JobFilters(company_size="huge"),
        JobFilters(job_type="gig"),
        JobFilters(radius=30),
    ],
)
def test_bad_filters_are_rejected(filters: JobFilters) -> None:
    with pytest.raises(ValueError):
        filters.params()


def test_listing_ids_from_ids_and_urls() -> None:
    assert listing_id(1010288405565) == 1010288405565
    assert listing_id(" 1010288405565 ") == 1010288405565
    assert (
        listing_id(
            "https://www.glassdoor.com/job-listing/software-engineer-lockheed-martin-"
            "JV_IC1132443_KO0,30_KE31,46.htm?jl=1010288405565&src=x"
        )
        == 1010288405565
    )
    assert (
        job_url("1010288405565") == "https://www.glassdoor.com/job-listing/JV.htm?jl=1010288405565"
    )
    with pytest.raises(ValueError):
        listing_id("not a job")


@pytest.mark.parametrize(
    "value",
    [
        3803,
        "3803",
        "E3803",
        "https://www.glassdoor.com/Reviews/Capgemini-Reviews-E3803.htm",
        "https://www.glassdoor.com/Overview/Working-at-Capgemini-EI_IE3803.11,20.htm",
        "https://www.glassdoor.com/Salary/Capgemini-Salaries-E3803_P2.htm",
        "/Reviews/Capgemini-Reviews-E3803.htm",
    ],
)
def test_company_ids_from_ids_and_urls(value: object) -> None:
    assert employer_id(value) == 3803  # type: ignore[arg-type]
    assert is_company_ref(value)  # type: ignore[arg-type]


def test_company_names_are_not_ids() -> None:
    assert not is_company_ref("Capgemini")
    assert not is_company_ref("3M")
    with pytest.raises(ValueError):
        employer_id("Bank of America")


def test_company_urls() -> None:
    assert overview_url(3803).endswith("/Overview/Working-at-Company-EI_IE3803.11,18.htm")
    assert salaries_url("Capgemini", 3803) == (
        "https://www.glassdoor.com/Salary/Capgemini-Salaries-E3803.htm"
    )
    assert salaries_url("Capgemini", 3803, 3, "Software Engineer") == (
        "https://www.glassdoor.com/Salary/Capgemini-Salaries-E3803_P3.htm"
        "?filter.jobTitleFTS=Software%20Engineer"
    )
    assert salary_path(
        "https://www.glassdoor.com/Salary/Bank-of-America-Salaries-E8874_P2.htm"
    ) == (
        "Bank-of-America",
        8874,
    )
    assert salary_path("https://www.glassdoor.com/Reviews/x-Reviews-E1.htm") is None
    with pytest.raises(ValueError):
        salaries_url("x", 1, 0)


def test_lookup_urls() -> None:
    assert company_search_url(" Bank of America ") == (
        "https://www.glassdoor.com/Search/results.htm?keyword=Bank%20of%20America"
    )
    assert location_lookup_url("Austin, TX").endswith(
        "locationTypeFilters=CITY%2CSTATE%2CCOUNTRY&caller=jobs&term=Austin%2C%20TX"
    )
