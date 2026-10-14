"""Benchmark pay at a company: base and total pay ranges for its most-reported job titles.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/salary_benchmark.py "Capgemini"

Glassdoor lists 10 job titles per page, most-reported first. This reads 3 pages and
saves them to salaries.csv.
"""

from __future__ import annotations

import sys

from glassdoor_scraper import GlassdoorScraper
from glassdoor_scraper.export import SALARY_COLUMNS, salary_rows, write_csv


def money(value: float | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def main(company: str) -> None:
    scraper = GlassdoorScraper()  # reads SCRAPEUNBLOCKER_KEY
    pages = list(scraper.iter_salaries(company, pages=3))
    rows = salary_rows(pages)
    if not rows:
        print(f"no salaries found for {company}")
        return

    first = pages[0]
    print(f"{first.company}: {first.job_title_count} job titles with salaries ({first.location})")
    for row in sorted(rows, key=lambda r: r["base_median"] or 0, reverse=True)[:10]:
        print(
            f"  {row['job_title'][:38]:<38} median {money(row['base_median']):>9} "
            f"{row['currency'] or ''}  (p10 {money(row['base_p10'])} - "
            f"p90 {money(row['base_p90'])}, {row['salary_count']} reports)"
        )
    write_csv(rows, "salaries.csv", SALARY_COLUMNS)
    print(f"wrote {len(rows)} job titles to salaries.csv")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Capgemini")
