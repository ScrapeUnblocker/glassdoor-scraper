"""Typed records the scraper returns. Every record has ``to_dict()`` for JSON/CSV."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]


@dataclass
class Location(_Record):
    """A Glassdoor location (from the location lookup)."""

    id: int
    type: str  # C = city, S = state, N = country, M = metro
    name: str
    long_name: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None


@dataclass
class Job(_Record):
    """One job from a search results page.

    The first 30 jobs of a search come from the page's embedded data and carry every
    field. Jobs loaded with "Show more jobs" (``pages > 1``) are read from the rendered
    job cards, which do not show ``age_days``, ``posted_date``, ``sponsored``,
    ``location_id``, ``occupation`` or ``salary_median`` - those stay ``None``.
    """

    listing_id: int
    title: str
    company: str | None = None
    company_id: int | None = None
    company_rating: float | None = None
    location: str | None = None
    location_id: int | None = None
    salary_min: float | None = None
    salary_median: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None  # annual, hourly, monthly, ...
    salary_source: str | None = None  # employer (provided by the employer) or estimate
    age_days: int | None = None
    posted_date: str | None = None  # derived from age_days on the day you scrape
    easy_apply: bool | None = None
    sponsored: bool | None = None
    occupation: str | None = None
    skills: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # job type, benefits, seniority, ...
    awards: list[str] = field(default_factory=list)
    snippet: str | None = None
    logo: str | None = None
    url: str | None = None


@dataclass
class JobSearchPage(_Record):
    """The result of one search: up to 30 jobs per page loaded."""

    url: str
    keyword: str | None
    location: str | None
    total: int | None  # jobs Glassdoor reports for the search
    pages_loaded: int
    complete: bool  # False if fewer "Show more jobs" pages loaded than requested
    filters: dict[str, Any] = field(default_factory=dict)  # filters Glassdoor applied
    jobs: list[Job] = field(default_factory=list)


@dataclass
class Ratings(_Record):
    """A company's ratings (1-5 stars; the ``*_pct`` fields are 0-100)."""

    overall: float | None = None
    career_opportunities: float | None = None
    compensation_benefits: float | None = None
    culture_values: float | None = None
    diversity_inclusion: float | None = None
    senior_management: float | None = None
    work_life_balance: float | None = None
    recommend_to_friend_pct: int | None = None
    ceo_approval_pct: int | None = None
    positive_outlook_pct: int | None = None
    review_count: int | None = None
    ceo_name: str | None = None


@dataclass
class ReviewHighlight(_Record):
    sentence: str
    sentiment: str | None = None
    review_count: int | None = None


@dataclass
class JobDetails(_Record):
    """Everything on a job page: the posting, the pay and the company."""

    listing_id: int
    title: str
    company: str | None = None
    company_id: int | None = None
    company_rating: float | None = None
    location: str | None = None
    location_id: int | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    salary_min: float | None = None
    salary_median: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    salary_source: str | None = None
    job_types: list[str] = field(default_factory=list)
    remote: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    age_days: int | None = None
    posted_date: str | None = None
    easy_apply: bool | None = None
    sponsored: bool | None = None
    expired: bool | None = None
    occupation: str | None = None
    description: str | None = None
    description_html: str | None = None
    company_legal_name: str | None = None
    company_headquarters: str | None = None
    company_size: str | None = None
    company_revenue: str | None = None
    company_type: str | None = None
    company_industry: str | None = None
    company_sector: str | None = None
    company_founded: int | None = None
    company_website: str | None = None
    company_logo: str | None = None
    company_ratings: Ratings | None = None
    company_review_count: int | None = None
    review_highlights: list[ReviewHighlight] = field(default_factory=list)
    benefits_rating: float | None = None
    benefits_review_count: int | None = None
    url: str | None = None


@dataclass
class Review(_Record):
    """One employee review."""

    review_id: int
    date: str | None = None
    title: str | None = None
    rating: float | None = None
    pros: str | None = None
    cons: str | None = None
    advice: str | None = None
    job_title: str | None = None
    location: str | None = None
    employment_status: str | None = None  # REGULAR, PART_TIME, CONTRACT, INTERN, ...
    current_employee: bool | None = None
    years_employed: int | None = None
    recommends: str | None = None  # POSITIVE, NEGATIVE or NEUTRAL
    ceo_opinion: str | None = None  # APPROVE, DISAPPROVE or NO_OPINION
    business_outlook: str | None = None  # POSITIVE, NEGATIVE or NEUTRAL
    career_opportunities: float | None = None
    compensation_benefits: float | None = None
    culture_values: float | None = None
    diversity_inclusion: float | None = None
    senior_management: float | None = None
    work_life_balance: float | None = None
    helpful_count: int | None = None
    employer_response: str | None = None


@dataclass
class Company(_Record):
    """A company profile: overview, ratings, rating distribution and reviews.

    ``reviews`` are the ones Glassdoor shows on the company page (up to 5, recent and
    featured); deeper review pages need a signed-in Glassdoor account.
    """

    id: int
    name: str | None = None
    legal_name: str | None = None
    website: str | None = None
    headquarters: str | None = None
    size: str | None = None
    founded: int | None = None
    revenue: str | None = None
    type: str | None = None
    industry: str | None = None
    sector: str | None = None
    stock: str | None = None
    description: str | None = None
    mission: str | None = None
    logo: str | None = None
    office_locations: int | None = None
    salary_count: int | None = None
    awards: list[str] = field(default_factory=list)
    ratings: Ratings | None = None
    industry_ratings: Ratings | None = None
    rating_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    reviews: list[Review] = field(default_factory=list)
    url: str | None = None
    reviews_url: str | None = None
    salaries_url: str | None = None
    jobs_url: str | None = None
    interviews_url: str | None = None


@dataclass
class CompanyMatch(_Record):
    """A company found by name."""

    id: int
    name: str | None = None
    legal_name: str | None = None
    rating: float | None = None
    logo: str | None = None


@dataclass
class Salary(_Record):
    """Pay for one job title at a company (percentiles of reported salaries)."""

    job_title: str
    job_title_id: int | None = None
    salary_count: int | None = None
    currency: str | None = None
    pay_period: str | None = None
    base_p10: float | None = None
    base_p25: float | None = None
    base_median: float | None = None
    base_p75: float | None = None
    base_p90: float | None = None
    total_p10: float | None = None
    total_p25: float | None = None
    total_median: float | None = None
    total_p75: float | None = None
    total_p90: float | None = None
    last_reported: str | None = None


@dataclass
class SalaryPage(_Record):
    """One page (up to 10 job titles) of a company's salaries."""

    url: str
    company_id: int
    company: str | None
    page: int
    pages: int | None
    job_title_count: int | None
    location: str | None
    salaries: list[Salary] = field(default_factory=list)
