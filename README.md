# Glassdoor Scraper

[![CI](https://github.com/ScrapeUnblocker/glassdoor-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/glassdoor-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [Glassdoor](https://www.glassdoor.com) into clean JSON or CSV: job search results with
salary ranges, full job postings, company profiles with ratings, the industry benchmark and
employee reviews, and company salaries by job title.** Search any keyword in any city, state or
country Glassdoor covers, with its own filters (date posted, salary, rating, remote, Easy Apply,
seniority, company size, job type, radius), and get typed Python records or a CSV from the
command line. Built for job boards and job alerts, salary benchmarking and compensation
research, employer-brand and competitor monitoring, recruiting market maps and labour-market
analytics.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
the `getPageSource` API fetches each Glassdoor page and returns its HTML, and clicks
"Show more jobs" in a real browser (with browser steps) when you ask for more than one page of
results. This package builds the Glassdoor URLs, reads the data each page ships with, and
retries transient failures. You don't need proxies, a headless browser or retry logic of your
own.

## Features

- **Job search.** Keyword and/or location: a city (`Austin, TX`), a state (`Texas`) or a country
  (`United Kingdom`), resolved through Glassdoor's own location lookup. Keywords stay exact, so
  `c++ developer` and `c# developer` search for what you typed.
- **Glassdoor's filters.** Posted in the last 1/3/7/14/30 days, newest first, minimum / maximum
  salary, minimum company rating, remote only, Easy Apply only, seniority, company size, job
  type, radius and a single company. The filters Glassdoor actually applied come back with every
  search, so you can check them.
- **Up to 150 jobs per search.** One request returns 30 jobs; `--pages 2..5` clicks
  "Show more jobs" in a real browser and returns up to 150 in that same request. Several
  keywords and locations run in one command, with duplicates removed.
- **Salaries as numbers.** Minimum, median and maximum, currency, pay period (annual, hourly,
  monthly) and whether the employer posted the pay or Glassdoor estimated it.
- **Job details.** The full description (as text and HTML), job types, remote options, education
  and skills, geolocation, posting date, the company's ratings, size, revenue, industry,
  founding year and HQ, review highlights and the benefits rating.
- **Company profiles.** Overview, website, size, revenue, founded, industry and sector, awards,
  overall and category ratings (career opportunities, compensation, culture, D&I, senior
  management, work-life balance), recommend-to-a-friend, CEO approval and business outlook
  shares, the **industry benchmark** for each rating, the 1-5 star distribution and the reviews
  shown on the profile (pros, cons, advice, job title, sub-ratings, employer response).
- **Salaries by job title.** Base and total pay percentiles (p10, p25, median, p75, p90),
  report count and last report date, 10 job titles per page, every page, optional job title.
- **Library + CLI.** Typed dataclasses, JSON / JSON Lines / CSV / terminal table output,
  retries with backoff, offline tests that never spend API credit.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/glassdoor-scraper.git
cd glassdoor-scraper
pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and set it (or copy `.env.example` to `.env` and load it your usual way):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here       # Windows PowerShell: $env:SCRAPEUNBLOCKER_KEY="your_key_here"
```

## Command line

```bash
# Data analyst jobs in Austin posted in the last week, as a table
glassdoor-scraper jobs "data analyst" --location "Austin, TX" --days 7 --format table

# Two roles x two locations (Glassdoor has a "Remote" location), 3 pages each, newest first, to CSV
glassdoor-scraper jobs "data engineer" "analytics engineer" -l "New York, NY" -l "Remote" \
    --sort newest --pages 3 -o jobs.csv

# Remote Python jobs paying 120k+ at companies rated 4+ stars, Easy Apply only
glassdoor-scraper jobs "python developer" --remote --min-salary 120000 --min-rating 4 --easy-apply

# Full details of jobs (listing IDs or job URLs)
glassdoor-scraper job 1010288405565 --pretty

# Company profiles side by side (names, IDs like E3803, or Glassdoor URLs)
glassdoor-scraper company "Capgemini" "Accenture" "Deloitte" --format csv -o companies.csv

# The reviews on those profiles, one row each
glassdoor-scraper reviews "Capgemini" "Accenture" -o reviews.csv

# Salaries by job title: 3 pages (30 titles), or one title
glassdoor-scraper salaries "Capgemini" --pages 3 -o salaries.csv
glassdoor-scraper salaries E3803 --job-title "Software Engineer" --format table

# Find a location (city, state or country) and its Glassdoor ID
glassdoor-scraper locations "London" --format table
```

| Command | What it returns |
| --- | --- |
| `jobs [KEYWORD ...]` | Job search results. Options: `-l/--location` (repeatable), `--days {1,3,7,14,30}`, `--sort {relevant,newest}`, `--min-salary`, `--max-salary`, `--min-rating {1-4}`, `--remote`, `--easy-apply`, `--seniority {entry,mid-senior,director,executive}`, `--company-size {1-200,201-500,501-1000,1001-5000,5001+}`, `--job-type {full-time,part-time,contract,temporary,permanent}`, `--radius {0,5,10,15,25,50,100}`, `--company-id`, `--pages 1-5`, `--limit` |
| `job ID_OR_URL ...` | Full job postings |
| `company NAME_ID_OR_URL ...` | Company profiles (JSON keeps everything; CSV/table give one summary row each) |
| `reviews NAME_ID_OR_URL ...` | The reviews on company profiles, one row each |
| `salaries NAME_ID_OR_URL` | Pay percentiles per job title. Options: `--pages`, `--start-page`, `--job-title` |
| `locations TERM` | Glassdoor locations matching a name, with their IDs |

Every command takes `-f/--format {json,jsonl,csv,table}` (default: from the `-o` file
extension, else JSON), `-o/--output FILE`, `--pretty`, `--retries`, `--timeout`, `--country`
(the country requests are routed through, default `us`) and `-q/--quiet`. Locations can also be
given by ID: `C:1139761` (city), `S:1347` (state), `N:2` (country).

## Library

```python
from glassdoor_scraper import GlassdoorScraper, JobFilters, unique_jobs

scraper = GlassdoorScraper()  # reads SCRAPEUNBLOCKER_KEY (or pass api_key="...")

# Search: 30 jobs per page, up to 5 pages in one request
page = scraper.search_jobs(
    "data analyst",
    "Austin, TX",
    filters=JobFilters(days=7, min_salary=70000, job_type="full-time"),
    pages=2,
)
print(page.total, page.filters)  # Glassdoor's count and the filters it applied
for job in page.jobs:
    print(job.title, "|", job.company, job.company_rating, "|", job.salary_min, job.salary_max)

# Several searches, each job once
pages = scraper.iter_searches(["data analyst", "data engineer"], ["Austin, TX", "Dallas, TX"])
jobs = unique_jobs(pages)

# A job page
details = scraper.job(page.jobs[0].listing_id)
print(details.description[:300], details.job_types, details.company_size)

# A company: profile, ratings vs. industry, star distribution, reviews
company = scraper.company("Capgemini")
print(
    company.ratings.overall,
    company.industry_ratings.overall,
    company.rating_distribution["overall"],
)
for review in company.reviews:
    print(review.date, review.rating, review.title, "| pros:", review.pros)

# Salaries by job title, every page up to 3
for salary_page in scraper.iter_salaries(company.id, pages=3):
    for salary in salary_page.salaries:
        print(salary.job_title, salary.base_median, salary.currency, salary.salary_count)
```

Errors: `GlassdoorNotFoundError` (no such job, company or location),
`GlassdoorParseError` (a page came back without its data, after retries); both subclass
`GlassdoorError`. Pass `client=` to use your own configured ScrapeUnblocker client.

## Example output

`glassdoor-scraper jobs "data analyst" --location "Austin, TX" --days 7 --format table`
(abridged):

```text
data analyst / Austin, TX: 15 jobs of 20
15 unique jobs
title                                     company                        company_rating  location    salary                  age_days  easy_apply
----------------------------------------  -----------------------------  --------------  ----------  ----------------------  --------  ----------
Financial Data Analyst                    IDR                                            Austin, TX                          0         True
Senior Data Analyst                       University of Texas at Austin  4.1             Austin, TX  90K USD/annual          0         False
SEMICON - Professionals                   Tokyo Electron                 3.8             Austin, TX  60K-113K USD/annual     0         False
Business Analyst, AI & Automation         Huckberry                      4.7             Austin, TX  56K-90K USD/annual      0         True
Sr. Business Intelligence Engineer, Dea~  Amazon Web Services            3.6             Austin, TX  130K-203K USD/annual    6         False
Consultant, Tax Technology                Ryan                           4.1             Austin, TX  102K-175K USD/annual    4         True
```

One job as JSON:

```json
{
  "listing_id": 1010166425436,
  "title": "Sr Backend Developer / Python",
  "company": "Intone Networks",
  "company_id": 375310,
  "company_rating": 4.0,
  "location": "New York, NY",
  "location_id": 1132348,
  "salary_min": 121647.0,
  "salary_median": 154811.0,
  "salary_max": 197016.0,
  "salary_currency": "USD",
  "salary_period": "annual",
  "salary_source": "estimate",
  "age_days": 124,
  "posted_date": "2026-06-12",
  "easy_apply": false,
  "sponsored": false,
  "occupation": "back end engineer",
  "skills": ["Python"],
  "tags": ["Software engineering", "8 years", "Contract", "Developing and maintaining backend systems", "Senior level"],
  "awards": [],
  "snippet": "Sr Backend Developer / Python • 8-10+ years of software engineering experience • Strong Python development experience.",
  "logo": "https://media.glassdoor.com/sql/375310/intone-networks-squarelogo.png",
  "url": "https://www.glassdoor.com/job-listing/sr-backend-developer-python-intone-networks-JV_IC1132348_KO0,27_KE28,43.htm?jl=1010166425436"
}
```

`python examples/company_report.py "Deloitte"` and `python examples/salary_benchmark.py E3803`:

```text
company              rating industry recommend   reviews
Deloitte                3.8     3.70       74%   139,017
    2026-10-12  5*  Career growth and learning opportunities, but long hours
    2014-08-04  5*  Great Place to start your career - Carefully read the cons

Capgemini: 2165 job titles with salaries (United States)
  Senior Manager                         median   170,363 USD  (p10 129,524 - p90 224,078, 538 reports)
  Solutions Architect 3                  median   151,075 USD  (p10 112,973 - p90 202,027, 565 reports)
  Senior Consultant                      median   141,046 USD  (p10 106,610 - p90 186,604, 3038 reports)
```

## Fields

| Record | Fields |
| --- | --- |
| `Job` (search results) | `listing_id`, `title`, `company`, `company_id`, `company_rating`, `location`, `location_id`, `salary_min` / `salary_median` / `salary_max`, `salary_currency`, `salary_period`, `salary_source` (`employer` or `estimate`), `age_days`, `posted_date`, `easy_apply`, `sponsored`, `occupation`, `skills`, `tags` (job type, benefits, seniority, ...), `awards`, `snippet`, `logo`, `url` |
| `JobDetails` (`job`) | everything above plus `region`, `country`, `postal_code`, `latitude`, `longitude`, `job_types`, `remote`, `education`, `experience`, `expired`, `description`, `description_html`, `company_legal_name`, `company_headquarters`, `company_size`, `company_revenue`, `company_type`, `company_industry`, `company_sector`, `company_founded`, `company_website`, `company_logo`, `company_ratings`, `company_review_count`, `review_highlights`, `benefits_rating`, `benefits_review_count` |
| `Company` (`company`) | `id`, `name`, `legal_name`, `website`, `headquarters`, `size`, `founded`, `revenue`, `type`, `industry`, `sector`, `stock`, `description`, `mission`, `logo`, `office_locations`, `salary_count`, `awards`, `ratings`, `industry_ratings`, `rating_distribution`, `reviews`, `url`, `reviews_url`, `salaries_url`, `jobs_url`, `interviews_url` |
| `Ratings` | `overall`, `career_opportunities`, `compensation_benefits`, `culture_values`, `diversity_inclusion`, `senior_management`, `work_life_balance` (1-5), `recommend_to_friend_pct`, `ceo_approval_pct`, `positive_outlook_pct` (0-100), `review_count`, `ceo_name` |
| `Review` | `review_id`, `date`, `title`, `rating`, `pros`, `cons`, `advice`, `job_title`, `location`, `employment_status`, `current_employee`, `years_employed`, `recommends`, `ceo_opinion`, `business_outlook`, six sub-ratings, `helpful_count`, `employer_response` |
| `Salary` (`salaries`) | `job_title`, `job_title_id`, `salary_count`, `currency`, `pay_period`, `base_p10` ... `base_p90`, `total_p10` ... `total_p90`, `last_reported` |

## Good to know

- **More than 150 jobs.** One search loads at most 5 pages (the first page plus four
  "Show more jobs" clicks fit in one request). For more coverage, split the search: several
  locations, `--days`, `--sort newest`, seniority, job type or company size. Duplicates across
  searches are removed.
- **Fields on later pages.** The first 30 jobs come from the page's embedded data and carry
  every field. Jobs loaded by "Show more jobs" are read from the job cards, which don't show
  `age_days`, `posted_date`, `sponsored`, `location_id`, `occupation`, `tags` or
  `salary_median`; card salaries are rounded the way Glassdoor prints them (`$88K`). Use
  `job` for the full record of any listing.
- **Totals.** `total` is the count Glassdoor reports for the search; the jobs it lists can be a
  little fewer.
- **Reviews.** You get the reviews Glassdoor shows on a company's public profile (up to 5,
  recent and featured) plus the full rating summary and star distribution. Further review
  pages require a signed-in Glassdoor account, and this package only reads public pages.
- **Salary job titles.** `--job-title` matches Glassdoor's own job title names
  (`Software Engineer`), not free text.
- **Locations outside the US** work too (`London, England`, `United Kingdom`, `Toronto, ON`);
  salaries come back in the local currency.
- Please use the data responsibly and in line with Glassdoor's terms and the laws that apply to
  you, especially for personal data in reviews.

## Project layout

```text
glassdoor-scraper/
├── src/glassdoor_scraper/
│   ├── __init__.py      # public API and __version__
│   ├── scraper.py       # GlassdoorScraper: search, job, company, salaries, lookups, retries
│   ├── parsing.py       # Glassdoor pages -> typed records (page data, job cards)
│   ├── flight.py        # reads the data payload Glassdoor's Next.js pages ship with
│   ├── urls.py          # search URLs, JobFilters, ID parsing, company URLs
│   ├── models.py        # Job, JobDetails, Company, Ratings, Review, Salary, Location, ...
│   ├── export.py        # JSON, JSON Lines, CSV rows and terminal tables
│   ├── cli.py           # the glassdoor-scraper command
│   └── __main__.py      # python -m glassdoor_scraper
├── examples/
│   ├── search_to_csv.py       # two roles in one city, last 14 days, to CSV
│   ├── company_report.py      # companies vs. their industry, with reviews
│   └── salary_benchmark.py    # top-paid job titles at a company, to CSV
├── tests/                     # offline tests with a mocked client (no API calls)
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .github/workflows/ci.yml
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install    # pip install -e ".[dev]"
make lint       # ruff check .
make format     # ruff format .
make test       # pytest -q (offline, no API key needed)
make run        # data analyst jobs in Austin from the last week, as a table (needs SCRAPEUNBLOCKER_KEY)
```

`pre-commit install` enables the ruff hooks from `.pre-commit-config.yaml`.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - web scraping API that returns HTML from protected sites
- [Documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - `getPageSource`, browser steps, SDKs, parameters and errors
- Official SDK: `pip install scrapeunblocker`

## License

[MIT](LICENSE) - Copyright (c) 2026 ScrapeUnblocker
