"""Compare companies on Glassdoor: ratings against their industry, plus reviews.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/company_report.py "Capgemini" "Accenture" "Deloitte"

Writes companies.json with every profile and prints a short comparison.
"""

from __future__ import annotations

import sys

from glassdoor_scraper import GlassdoorNotFoundError, GlassdoorScraper, Ratings
from glassdoor_scraper.export import to_json


def main(names: list[str]) -> None:
    scraper = GlassdoorScraper()  # reads SCRAPEUNBLOCKER_KEY
    companies = []
    for name in names:
        try:
            companies.append(scraper.company(name))
        except GlassdoorNotFoundError as error:
            print(f"skipped {name}: {error}")

    print(f"{'company':<20} {'rating':>6} {'industry':>8} {'recommend':>9} {'reviews':>9}")
    for company in companies:
        ours, industry = company.ratings or Ratings(), company.industry_ratings
        print(
            f"{(company.name or '?'):<20} {ours.overall or 0:>6.1f} "
            f"{(industry.overall if industry else 0) or 0:>8.2f} "
            f"{ours.recommend_to_friend_pct or 0:>8}% {ours.review_count or 0:>9,}"
        )
        for review in company.reviews[:2]:
            print(f"    {review.date}  {review.rating or 0:.0f}*  {review.title}")

    with open("companies.json", "w", encoding="utf-8") as handle:
        handle.write(to_json(companies, pretty=True))
    print("wrote companies.json")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Capgemini", "Accenture"])
