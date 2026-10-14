"""Command-line interface: ``glassdoor-scraper <command> ...``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, TextIO

from . import __version__
from .export import (
    COMPANY_COLUMNS,
    JOB_COLUMNS,
    JOB_DETAIL_COLUMNS,
    LOCATION_COLUMNS,
    REVIEW_COLUMNS,
    SALARY_COLUMNS,
    company_row,
    csv_string,
    flat_row,
    job_detail_row,
    review_rows,
    salary_rows,
    table,
    to_json,
    to_jsonl,
)
from .parsing import GlassdoorError
from .scraper import MAX_PAGES, GlassdoorScraper, unique_jobs
from .urls import COMPANY_SIZES, DATE_POSTED, JOB_TYPES, RADII, SENIORITY, SORTS, JobFilters

FORMATS = ("json", "jsonl", "csv", "table")
_EXTENSIONS = {".json": "json", ".jsonl": "jsonl", ".csv": "csv", ".txt": "table"}

JOB_TABLE = ("title", "company", "company_rating", "location", "salary", "age_days", "easy_apply")
DETAIL_TABLE = ("title", "company", "location", "salary", "job_types", "posted_date", "skills")
COMPANY_TABLE = (
    "name",
    "rating_overall",
    "review_count",
    "recommend_to_friend_pct",
    "ceo_approval_pct",
    "industry_rating_overall",
    "size",
    "headquarters",
)
REVIEW_TABLE = ("company", "date", "rating", "title", "job_title", "location", "recommends")
SALARY_TABLE = (
    "company",
    "job_title",
    "salary_count",
    "currency",
    "base_p10",
    "base_median",
    "base_p90",
    "total_median",
)
LOCATION_TABLE = ("id", "type", "name", "country")


def _stdout() -> TextIO:
    """stdout that always accepts UTF-8 (Windows consoles default to a legacy codepage)."""
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # pragma: no cover - exotic streams
            pass
    return stream


def _log(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, file=sys.stderr, flush=True)


def _money(value: float | None) -> str:
    if value is None:
        return ""
    if value >= 10_000:
        return f"{value / 1000:.0f}K"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def salary_label(row: dict[str, Any]) -> str:
    """``{"salary_min": 88000, "salary_max": 146000, ...}`` -> ``"88K-146K USD/annual"``."""
    low, high = row.get("salary_min"), row.get("salary_max")
    if low is None and high is None:
        return ""
    span = _money(low) if low == high or high is None else f"{_money(low)}-{_money(high)}"
    unit = "/".join(
        str(part) for part in (row.get("salary_currency"), row.get("salary_period")) if part
    )
    return f"{span} {unit}".strip()


def _add_common(parser: argparse.ArgumentParser, *, formats: Sequence[str] = FORMATS) -> None:
    parser.add_argument(
        "-f",
        "--format",
        choices=formats,
        help="output format (default: from the -o extension, else json)",
    )
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    parser.add_argument(
        "--country",
        default="us",
        help="country to route requests through (default: us)",
    )
    parser.add_argument("--retries", type=int, default=3, help="retries per request (default: 3)")
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="seconds per request (default: 180)"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="no progress messages")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glassdoor-scraper",
        description=(
            "Scrape Glassdoor jobs, job details, company ratings and reviews, and salaries "
            "via the ScrapeUnblocker API. Set SCRAPEUNBLOCKER_KEY first."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    jobs = commands.add_parser("jobs", help="search jobs by keyword and/or location")
    jobs.add_argument(
        "keywords", nargs="*", help="job keywords, e.g. 'data analyst' (one search each)"
    )
    jobs.add_argument(
        "-l",
        "--location",
        action="append",
        default=[],
        help="city, state or country, e.g. 'Austin, TX' (repeatable; default: United States)",
    )
    jobs.add_argument("--days", type=int, choices=DATE_POSTED, help="posted in the last N days")
    jobs.add_argument("--sort", choices=tuple(SORTS), help="relevant (default) or newest")
    jobs.add_argument("--min-salary", type=int, help="minimum salary (local currency)")
    jobs.add_argument("--max-salary", type=int, help="maximum salary (local currency)")
    jobs.add_argument(
        "--min-rating", type=int, choices=(1, 2, 3, 4), help="minimum company rating (stars)"
    )
    jobs.add_argument("--remote", action="store_true", help="remote / work-from-home jobs only")
    jobs.add_argument("--easy-apply", action="store_true", help="Easy Apply jobs only")
    jobs.add_argument("--seniority", choices=tuple(SENIORITY), help="seniority level")
    jobs.add_argument("--company-size", choices=tuple(COMPANY_SIZES), help="employees")
    jobs.add_argument("--job-type", choices=tuple(JOB_TYPES), help="job type")
    jobs.add_argument("--radius", type=int, choices=RADII, help="miles around the location")
    jobs.add_argument("--company-id", type=int, help="only jobs at this Glassdoor company ID")
    jobs.add_argument(
        "--pages",
        type=int,
        default=1,
        choices=range(1, MAX_PAGES + 1),
        metavar=f"1-{MAX_PAGES}",
        help="result pages per search, 30 jobs each (default: 1)",
    )
    jobs.add_argument("--limit", type=int, help="stop after this many jobs in total")
    _add_common(jobs)

    job = commands.add_parser("job", help="full details of jobs by listing ID or URL")
    job.add_argument("jobs", nargs="+", help="listing IDs (jl=...) or Glassdoor job URLs")
    _add_common(job)

    company = commands.add_parser("company", help="company profiles: details, ratings and reviews")
    company.add_argument("companies", nargs="+", help="company names, IDs (E3803) or URLs")
    _add_common(company)

    reviews = commands.add_parser(
        "reviews", help="the reviews on company profiles (recent and featured)"
    )
    reviews.add_argument("companies", nargs="+", help="company names, IDs (E3803) or URLs")
    _add_common(reviews)

    salaries = commands.add_parser("salaries", help="a company's salaries by job title")
    salaries.add_argument("company", help="company name, ID (E3803) or URL")
    salaries.add_argument(
        "--pages", type=int, default=1, help="pages of 10 job titles (default: 1)"
    )
    salaries.add_argument("--start-page", type=int, default=1, help="first page (default: 1)")
    salaries.add_argument("--job-title", help="only this job title, e.g. 'Software Engineer'")
    _add_common(salaries)

    locations = commands.add_parser("locations", help="look up Glassdoor locations")
    locations.add_argument("term", help="place name, e.g. 'London'")
    _add_common(locations)
    return parser


def _format(args: argparse.Namespace, default: str = "json") -> str:
    if args.format:
        return args.format
    if args.output:
        return _EXTENSIONS.get(Path(args.output).suffix.lower(), default)
    return default


def _write(args: argparse.Namespace, text: str) -> None:
    if args.output:
        encoding = "utf-8-sig" if _format(args) == "csv" else "utf-8"
        with open(args.output, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        _log(args, f"wrote {args.output}")
    else:
        stream = _stdout()
        stream.write(text if text.endswith("\n") else text + "\n")
        stream.flush()


def _render(
    args: argparse.Namespace,
    records: Any,
    rows: list[dict[str, Any]],
    columns: Sequence[str],
    table_columns: Sequence[str],
) -> str:
    fmt = _format(args)
    if fmt == "json":
        return to_json(records, pretty=args.pretty)
    if fmt == "jsonl":
        return to_jsonl(records if isinstance(records, list) else [records])
    if fmt == "csv":
        return csv_string(rows, columns)
    return table(rows, table_columns)


def _scraper(args: argparse.Namespace) -> GlassdoorScraper:
    def on_retry(attempt: int, delay: float, error: BaseException) -> None:
        _log(args, f"  retry {attempt} in {delay:.0f}s ({type(error).__name__})")

    return GlassdoorScraper(
        country=args.country,
        retries=args.retries,
        timeout=args.timeout,
        on_retry=on_retry,
    )


def _filters(args: argparse.Namespace) -> JobFilters:
    return JobFilters(
        days=args.days,
        sort=args.sort,
        min_salary=args.min_salary,
        max_salary=args.max_salary,
        min_rating=args.min_rating,
        remote=args.remote,
        easy_apply=args.easy_apply,
        seniority=args.seniority,
        company_size=args.company_size,
        job_type=args.job_type,
        radius=args.radius,
        company_id=args.company_id,
    )


def _with_salary(row: dict[str, Any], record: Any) -> dict[str, Any]:
    row["salary"] = salary_label(record.to_dict())
    return row


def cmd_jobs(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    if not args.keywords and not args.location:
        raise SystemExit("give a keyword, a --location, or both")
    filters = _filters(args)
    filters.params()  # validate before spending any requests
    failed = 0

    def on_error(keyword: Any, place: Any, error: Exception) -> None:
        nonlocal failed
        failed += 1
        _log(args, f"  search {keyword or '-'} / {place or '-'} failed: {error}")

    pages = []
    for page in scraper.iter_searches(
        args.keywords or [None],
        args.location or [None],
        filters=filters,
        pages=args.pages,
        on_error=on_error,
    ):
        note = "" if page.complete else " (fewer pages than asked)"
        _log(
            args,
            f"{page.keyword or '-'} / {page.location or 'United States'}: "
            f"{len(page.jobs)} jobs of {page.total if page.total is not None else '?'}{note}",
        )
        pages.append(page)
    jobs = unique_jobs(pages)
    if args.limit is not None:
        jobs = jobs[: max(0, args.limit)]
    _log(args, f"{len(jobs)} unique jobs")
    rows = [_with_salary(flat_row(job, JOB_COLUMNS), job) for job in jobs]
    _write(args, _render(args, jobs, rows, JOB_COLUMNS, JOB_TABLE))
    return 1 if failed and not jobs else 0


def _each(
    args: argparse.Namespace,
    values: Sequence[str],
    action: Callable[[str], Any],
    label: str,
) -> tuple[list[Any], int]:
    results, failed = [], 0
    for value in values:
        try:
            results.append(action(value))
            _log(args, f"{label} {value}: ok")
        except GlassdoorError as exc:
            failed += 1
            _log(args, f"{label} {value}: {exc}")
    return results, failed


def cmd_job(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    details, failed = _each(args, args.jobs, scraper.job, "job")
    rows = [_with_salary(job_detail_row(job), job) for job in details]
    _write(args, _render(args, details, rows, JOB_DETAIL_COLUMNS, DETAIL_TABLE))
    return 1 if failed else 0


def cmd_company(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    companies, failed = _each(args, args.companies, scraper.company, "company")
    rows = [company_row(company) for company in companies]
    _write(args, _render(args, companies, rows, COMPANY_COLUMNS, COMPANY_TABLE))
    return 1 if failed else 0


def cmd_reviews(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    companies, failed = _each(args, args.companies, scraper.company, "company")
    rows = [row for company in companies for row in review_rows(company)]
    _write(args, _render(args, rows, rows, REVIEW_COLUMNS, REVIEW_TABLE))
    return 1 if failed else 0


def cmd_salaries(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    if args.pages < 1 or args.start_page < 1:
        raise SystemExit("--pages and --start-page must be 1 or more")
    pages = []
    for page in scraper.iter_salaries(
        args.company, pages=args.pages, start_page=args.start_page, job_title=args.job_title
    ):
        _log(
            args,
            f"{page.company or page.company_id}: page {page.page}/{page.pages or '?'}, "
            f"{len(page.salaries)} job titles",
        )
        pages.append(page)
    rows = salary_rows(pages)
    _write(args, _render(args, rows, rows, SALARY_COLUMNS, SALARY_TABLE))
    return 0


def cmd_locations(args: argparse.Namespace, scraper: GlassdoorScraper) -> int:
    locations = scraper.locations(args.term)
    rows = [flat_row(location, LOCATION_COLUMNS) for location in locations]
    _write(args, _render(args, locations, rows, LOCATION_COLUMNS, LOCATION_TABLE))
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace, GlassdoorScraper], int]] = {
    "jobs": cmd_jobs,
    "job": cmd_job,
    "company": cmd_company,
    "reviews": cmd_reviews,
    "salaries": cmd_salaries,
    "locations": cmd_locations,
}


def main(
    argv: Sequence[str] | None = None,
    scraper_factory: Callable[[argparse.Namespace], GlassdoorScraper] = _scraper,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, scraper_factory(args))
    except (GlassdoorError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if any(cls.__name__ == "ScrapeUnblockerError" for cls in type(exc).__mro__):
            print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        raise
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
