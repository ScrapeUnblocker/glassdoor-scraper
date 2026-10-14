from __future__ import annotations

import csv
import json

import pytest

from glassdoor_scraper import GlassdoorScraper, __version__
from glassdoor_scraper.cli import build_parser, main, salary_label

from . import pages
from .conftest import FakeClient, TargetNotFoundError


def run(argv: list[str], client: FakeClient) -> int:
    def factory(args) -> GlassdoorScraper:
        return GlassdoorScraper(client=client, sleep=lambda seconds: None, transient_errors=())

    return main(argv, scraper_factory=factory)


def test_parser_reads_job_search_options() -> None:
    args = build_parser().parse_args(
        [
            "jobs",
            "data analyst",
            "python developer",
            "-l",
            "Austin, TX",
            "-l",
            "Remote",
            "--days",
            "7",
            "--sort",
            "newest",
            "--min-salary",
            "90000",
            "--remote",
            "--easy-apply",
            "--company-size",
            "5001+",
            "--job-type",
            "full-time",
            "--pages",
            "3",
            "-o",
            "jobs.csv",
        ]
    )
    assert args.keywords == ["data analyst", "python developer"]
    assert args.location == ["Austin, TX", "Remote"]
    assert (args.days, args.sort, args.min_salary, args.pages) == (7, "newest", 90000, 3)
    assert args.remote and args.easy_apply
    assert (args.company_size, args.job_type) == ("5001+", "full-time")


@pytest.mark.parametrize(
    "argv",
    [
        ["jobs", "x", "--pages", "6"],
        ["jobs", "x", "--days", "5"],
        ["jobs", "x", "--seniority", "intern"],
        ["company"],
        ["nope"],
    ],
)
def test_parser_rejects_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_version(capsys) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--version"])
    assert __version__ in capsys.readouterr().out


def test_jobs_to_csv(tmp_path, capsys) -> None:
    client = FakeClient([("/Job/", pages.search_page())])
    out = tmp_path / "jobs.csv"
    assert run(["jobs", "python developer", "python", "-o", str(out)], client) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert [row["listing_id"] for row in rows] == ["1001", "1002"]  # deduped across searches
    assert rows[0]["skills"] == "Python"
    assert rows[0]["tags"] == "401(k) | Full-time"
    assert len(client.calls) == 2
    assert "2 unique jobs" in capsys.readouterr().err


def test_jobs_json_to_stdout_with_limit(capsys) -> None:
    client = FakeClient([("/Job/", pages.search_page())])
    assert run(["jobs", "python", "--limit", "1", "-q"], client) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1 and data[0]["salary_period"] == "hourly"


def test_jobs_table(capsys) -> None:
    client = FakeClient([("/Job/", pages.search_page())])
    assert run(["jobs", "python", "-f", "table", "-q"], client) == 0
    out = capsys.readouterr().out
    assert "Python Developer" in out and "60-65 USD/hourly" in out


def test_jobs_needs_a_keyword_or_location() -> None:
    with pytest.raises(SystemExit):
        run(["jobs"], FakeClient())


def test_jobs_bad_salary_range_fails_before_any_request(capsys) -> None:
    client = FakeClient()
    assert run(["jobs", "x", "--min-salary", "100", "--max-salary", "50"], client) == 1
    assert client.calls == [] and "max_salary" in capsys.readouterr().err


def test_job_details_partial_failure_exit_code(capsys) -> None:
    client = FakeClient(
        [("jl=42", TargetNotFoundError("404")), ("/job-listing/", pages.job_page())]
    )
    code = run(["job", "42", "1010288405565", "-f", "jsonl", "-q"], client)
    lines = capsys.readouterr().out.strip().splitlines()
    assert code == 1 and len(lines) == 1
    assert json.loads(lines[0])["company_revenue"] == "$10+ billion (USD)"


def test_company_and_reviews(tmp_path, capsys) -> None:
    client = FakeClient([("/Overview/", pages.company_page())])
    assert run(["company", "E123", "-f", "csv", "-q"], client) == 0
    (row,) = list(csv.DictReader(capsys.readouterr().out.splitlines()))
    assert row["name"] == "Acme" and row["rating_overall"] == "4.3"
    assert row["industry_rating_overall"] == "3.63" and row["ceo_name"] == "Wile E. Coyote"

    out = tmp_path / "reviews.json"
    assert run(["reviews", "123", "-o", str(out), "-q"], client) == 0
    reviews = json.loads(out.read_text(encoding="utf-8"))
    assert [r["review_id"] for r in reviews] == [9001, 9002]
    assert reviews[0]["company"] == "Acme"


def test_salaries_pages(capsys) -> None:
    client = FakeClient(
        [
            ("_P2.htm", pages.salaries_page(page=2)),
            ("/Salary/", pages.salaries_page(page=1)),
        ]
    )
    url = "https://www.glassdoor.com/Salary/Acme-Salaries-E123.htm"
    assert run(["salaries", url, "--pages", "3", "-f", "csv"], client) == 0
    captured = capsys.readouterr()
    rows = list(csv.DictReader(captured.out.splitlines()))
    assert [row["job_title"] for row in rows] == ["Senior Consultant 1", "Senior Consultant 2"]
    assert "page 2/2" in captured.err


def test_locations(capsys) -> None:
    client = FakeClient([("/autocomplete/location", pages.LOCATIONS)])
    assert run(["locations", "austin", "-f", "table"], client) == 0
    assert "Austin, TX" in capsys.readouterr().out


def test_glassdoor_errors_exit_1(capsys) -> None:
    client = FakeClient([("/autocomplete/location", "[]")])
    assert run(["jobs", "nurse", "-l", "Atlantis"], client) == 1  # every search failed
    assert "failed" in capsys.readouterr().err
    assert run(["salaries", "E1"], FakeClient([("/Overview/", TargetNotFoundError("404"))])) == 1


@pytest.mark.parametrize(
    ("row", "label"),
    [
        ({"salary_min": 88000, "salary_max": 146000, "salary_currency": "USD",
          "salary_period": "annual"}, "88K-146K USD/annual"),
        ({"salary_min": 26.73, "salary_max": 34.78, "salary_currency": "USD",
          "salary_period": "hourly"}, "26.73-34.78 USD/hourly"),
        ({"salary_min": 90000, "salary_max": 90000, "salary_currency": "GBP"}, "90K GBP"),
        ({"salary_min": None, "salary_max": None}, ""),
    ],
)  # fmt: skip
def test_salary_label(row: dict, label: str) -> None:
    assert salary_label(row) == label
