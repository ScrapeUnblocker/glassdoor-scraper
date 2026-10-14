"""Write results as JSON, JSON Lines, CSV or a quick terminal table."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .models import Company, JobDetails

LIST_SEPARATOR = " | "

JOB_COLUMNS = (
    "listing_id",
    "title",
    "company",
    "company_id",
    "company_rating",
    "location",
    "location_id",
    "salary_min",
    "salary_median",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_source",
    "age_days",
    "posted_date",
    "easy_apply",
    "sponsored",
    "occupation",
    "skills",
    "tags",
    "awards",
    "snippet",
    "logo",
    "url",
)

JOB_DETAIL_COLUMNS = (
    "listing_id",
    "title",
    "company",
    "company_id",
    "company_rating",
    "location",
    "region",
    "country",
    "latitude",
    "longitude",
    "salary_min",
    "salary_median",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_source",
    "job_types",
    "remote",
    "education",
    "experience",
    "skills",
    "age_days",
    "posted_date",
    "easy_apply",
    "sponsored",
    "expired",
    "occupation",
    "company_size",
    "company_industry",
    "company_sector",
    "company_headquarters",
    "company_founded",
    "company_revenue",
    "company_type",
    "company_website",
    "company_review_count",
    "benefits_rating",
    "url",
    "description",
)

REVIEW_COLUMNS = (
    "company_id",
    "company",
    "review_id",
    "date",
    "title",
    "rating",
    "pros",
    "cons",
    "advice",
    "job_title",
    "location",
    "employment_status",
    "current_employee",
    "years_employed",
    "recommends",
    "ceo_opinion",
    "business_outlook",
    "career_opportunities",
    "compensation_benefits",
    "culture_values",
    "diversity_inclusion",
    "senior_management",
    "work_life_balance",
    "helpful_count",
    "employer_response",
)

COMPANY_COLUMNS = (
    "id",
    "name",
    "legal_name",
    "website",
    "headquarters",
    "size",
    "founded",
    "revenue",
    "type",
    "industry",
    "sector",
    "rating_overall",
    "rating_career_opportunities",
    "rating_compensation_benefits",
    "rating_culture_values",
    "rating_diversity_inclusion",
    "rating_senior_management",
    "rating_work_life_balance",
    "recommend_to_friend_pct",
    "ceo_approval_pct",
    "positive_outlook_pct",
    "review_count",
    "ceo_name",
    "industry_rating_overall",
    "office_locations",
    "salary_count",
    "url",
)

SALARY_COLUMNS = (
    "company_id",
    "company",
    "job_title",
    "salary_count",
    "currency",
    "pay_period",
    "base_p10",
    "base_p25",
    "base_median",
    "base_p75",
    "base_p90",
    "total_p10",
    "total_p25",
    "total_median",
    "total_p75",
    "total_p90",
    "last_reported",
)

LOCATION_COLUMNS = ("id", "type", "name", "long_name", "city", "state", "country", "country_code")


def to_dict(record: Any) -> dict[str, Any]:
    """A record (dataclass with ``to_dict`` or a dict) as a plain dict."""
    if hasattr(record, "to_dict"):
        return record.to_dict()
    if isinstance(record, dict):
        return dict(record)
    raise TypeError(f"cannot export {type(record).__name__}")


def to_json(data: Any, *, pretty: bool = False) -> str:
    """Serialize a record, or a list of records, as JSON."""
    if isinstance(data, (list, tuple)):
        payload: Any = [to_dict(item) for item in data]
    else:
        payload = to_dict(data)
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def to_jsonl(records: Iterable[Any]) -> str:
    """Serialize records as JSON Lines (one object per line)."""
    return "".join(json.dumps(to_dict(r), ensure_ascii=False) + "\n" for r in records)


def _cell(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return LIST_SEPARATOR.join(str(item) for item in value if item not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def flat_row(record: Any, columns: Sequence[str] | None = None) -> dict[str, Any]:
    """A record as one flat CSV row (lists joined with `` | ``)."""
    data = to_dict(record)
    keys = columns or [key for key, value in data.items() if not isinstance(value, dict)]
    return {key: _cell(data.get(key)) for key in keys}


def job_detail_row(job: JobDetails) -> dict[str, Any]:
    return flat_row(job, JOB_DETAIL_COLUMNS)


def company_row(company: Company) -> dict[str, Any]:
    """A company profile as one flat row (ratings spread into columns)."""
    data = to_dict(company)
    ratings = data.get("ratings") or {}
    industry = data.get("industry_ratings") or {}
    row = {key: _cell(data.get(key)) for key in COMPANY_COLUMNS if key in data}
    for name in (
        "overall",
        "career_opportunities",
        "compensation_benefits",
        "culture_values",
        "diversity_inclusion",
        "senior_management",
        "work_life_balance",
    ):
        row[f"rating_{name}"] = ratings.get(name)
    for name in (
        "recommend_to_friend_pct",
        "ceo_approval_pct",
        "positive_outlook_pct",
        "review_count",
        "ceo_name",
    ):
        row[name] = ratings.get(name)
    row["industry_rating_overall"] = industry.get("overall")
    return {key: row.get(key) for key in COMPANY_COLUMNS}


def review_rows(company: Company) -> list[dict[str, Any]]:
    """A company's reviews as flat rows (with the company ID and name on each)."""
    rows = []
    for review in company.reviews:
        row = flat_row(review)
        row.update(company_id=company.id, company=company.name)
        rows.append({key: row.get(key) for key in REVIEW_COLUMNS})
    return rows


def salary_rows(pages: Iterable[Any]) -> list[dict[str, Any]]:
    """Salary pages as flat rows, one per job title."""
    rows = []
    for page in pages:
        for salary in page.salaries:
            row = flat_row(salary)
            row.update(company_id=page.company_id, company=page.company)
            rows.append({key: row.get(key) for key in SALARY_COLUMNS})
    return rows


def csv_string(rows: Iterable[dict[str, Any]], columns: Sequence[str]) -> str:
    """Rows as CSV text with a header."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _cell(row.get(key)) for key in columns})
    return buffer.getvalue()


def write_csv(rows: Iterable[dict[str, Any]], path: str | Path, columns: Sequence[str]) -> int:
    """Write rows to a CSV file (UTF-8 with BOM so Excel opens it cleanly)."""
    rows = list(rows)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(csv_string(rows, columns))
    return len(rows)


def table(rows: Sequence[dict[str, Any]], columns: Sequence[str], *, width: int = 40) -> str:
    """A plain-text table for a quick look in the terminal."""

    def show(value: Any) -> str:
        text = "" if value is None else str(_cell(value))
        text = " ".join(text.split())
        return text if len(text) <= width else text[: width - 1] + "~"

    cells = [[show(row.get(column)) for column in columns] for row in rows]
    widths = [
        max([len(column)] + [len(line[index]) for line in cells])
        for index, column in enumerate(columns)
    ]
    lines = ["  ".join(column.ljust(widths[i]) for i, column in enumerate(columns))]
    lines.append("  ".join("-" * widths[i] for i in range(len(columns))))
    lines += ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)) for line in cells]
    return "\n".join(lines)
