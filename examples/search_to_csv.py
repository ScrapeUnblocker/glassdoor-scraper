"""Search Glassdoor for several roles in one city and save the jobs to CSV.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/search_to_csv.py

Each search returns up to 60 jobs here (2 pages). Jobs that match more than one
role are written once.
"""

from __future__ import annotations

from glassdoor_scraper import GlassdoorScraper, JobFilters, unique_jobs
from glassdoor_scraper.export import JOB_COLUMNS, flat_row, write_csv

ROLES = ["data analyst", "data engineer"]
LOCATION = "Austin, TX"


def main() -> None:
    scraper = GlassdoorScraper()  # reads SCRAPEUNBLOCKER_KEY
    filters = JobFilters(days=14, sort="newest")
    pages = []
    for role in ROLES:
        page = scraper.search_jobs(role, LOCATION, filters=filters, pages=2)
        print(f"{role}: {len(page.jobs)} of {page.total} jobs in {page.location}")
        pages.append(page)

    jobs = unique_jobs(pages)
    with_pay = [job for job in jobs if job.salary_min is not None]
    count = write_csv((flat_row(job, JOB_COLUMNS) for job in jobs), "jobs.csv", JOB_COLUMNS)
    print(f"wrote {count} jobs to jobs.csv ({len(with_pay)} show a salary)")


if __name__ == "__main__":
    main()
