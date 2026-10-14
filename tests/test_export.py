from __future__ import annotations

import csv
import json

from glassdoor_scraper.export import (
    JOB_COLUMNS,
    SALARY_COLUMNS,
    company_row,
    csv_string,
    flat_row,
    review_rows,
    salary_rows,
    table,
    to_json,
    to_jsonl,
    write_csv,
)
from glassdoor_scraper.parsing import parse_company_page, parse_salaries_page, parse_search_page

from . import pages


def _jobs():
    return parse_search_page(pages.search_page(), "https://x").jobs


def test_json_and_jsonl() -> None:
    jobs = _jobs()
    data = json.loads(to_json(jobs, pretty=True))
    assert data[0]["listing_id"] == 1001 and data[0]["skills"] == ["Python"]
    lines = to_jsonl(jobs).splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["title"] == "Data Engineer"


def test_flat_rows_join_lists() -> None:
    row = flat_row(_jobs()[0], JOB_COLUMNS)
    assert list(row) == list(JOB_COLUMNS)
    assert row["tags"] == "401(k) | Full-time"


def test_csv_file_round_trip(tmp_path) -> None:
    path = tmp_path / "jobs.csv"
    rows = [flat_row(job, JOB_COLUMNS) for job in _jobs()]
    assert write_csv(rows, path, JOB_COLUMNS) == 2
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
    read = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert read[1]["company"] == "Globex"


def test_company_review_and_salary_rows() -> None:
    company = parse_company_page(pages.company_page(), "https://x", 123)
    row = company_row(company)
    assert row["rating_overall"] == 4.3 and row["recommend_to_friend_pct"] == 88
    assert row["review_count"] == 1052 and row["founded"] == 1949
    reviews = review_rows(company)
    assert [r["review_id"] for r in reviews] == [9001, 9002]
    assert reviews[0]["company"] == "Acme" and reviews[0]["pros"] == "Great team"

    salary_page = parse_salaries_page(pages.salaries_page(), "https://x", 123)
    (salary,) = salary_rows([salary_page])
    assert list(salary) == list(SALARY_COLUMNS)
    assert salary["company"] == "Acme" and salary["base_median"] == 120001


def test_csv_string_and_table() -> None:
    rows = [{"a": "x" * 50, "b": ["one", "two"]}, {"a": None, "b": []}]
    text = csv_string(rows, ["a", "b"])
    assert text.splitlines()[0] == "a,b" and "one | two" in text
    shown = table(rows, ["a", "b"], width=10)
    assert "xxxxxxxxx~" in shown and "one | two" in shown
