"""Scrape Glassdoor jobs, job details, company profiles, reviews and salaries.

Powered by the ScrapeUnblocker ``getPageSource`` API
(https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos).

Quick start::

    from glassdoor_scraper import GlassdoorScraper, JobFilters

    scraper = GlassdoorScraper()  # reads SCRAPEUNBLOCKER_KEY
    page = scraper.search_jobs("data analyst", "Austin, TX", filters=JobFilters(days=7))
    for job in page.jobs:
        print(job.title, job.company, job.salary_min, job.salary_max)

    details = scraper.job(page.jobs[0].listing_id)
    company = scraper.company("Capgemini")
    salaries = scraper.salaries(company.id)
"""

from .models import (
    Company,
    CompanyMatch,
    Job,
    JobDetails,
    JobSearchPage,
    Location,
    Ratings,
    Review,
    ReviewHighlight,
    Salary,
    SalaryPage,
)
from .parsing import (
    GlassdoorError,
    GlassdoorNotFoundError,
    GlassdoorParseError,
    parse_company_page,
    parse_job_page,
    parse_salaries_page,
    parse_salary_text,
    parse_search_page,
)
from .scraper import MAX_PAGES, PAGE_SIZE, GlassdoorScraper, load_more_steps, unique_jobs
from .urls import JobFilters, job_url, search_url

__version__ = "0.1.0"

__all__ = [
    "MAX_PAGES",
    "PAGE_SIZE",
    "Company",
    "CompanyMatch",
    "GlassdoorError",
    "GlassdoorNotFoundError",
    "GlassdoorParseError",
    "GlassdoorScraper",
    "Job",
    "JobDetails",
    "JobFilters",
    "JobSearchPage",
    "Location",
    "Ratings",
    "Review",
    "ReviewHighlight",
    "Salary",
    "SalaryPage",
    "__version__",
    "job_url",
    "load_more_steps",
    "parse_company_page",
    "parse_job_page",
    "parse_salaries_page",
    "parse_salary_text",
    "parse_search_page",
    "search_url",
    "unique_jobs",
]
