"""Glassdoor URLs: job search (with filters), job pages, company pages and lookups."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse

BASE_URL = "https://www.glassdoor.com"

#: Glassdoor location types, as used in search URLs (``locT``) and lookups.
LOCATION_TYPES = {"C": "city", "S": "state", "N": "country", "M": "metro"}

#: ``--days`` values the site offers ("posted in the last N days").
DATE_POSTED = (1, 3, 7, 14, 30)

SORTS = {"relevant": "", "newest": "date_desc"}

SENIORITY = {
    "entry": "entrylevel",
    "mid-senior": "midseniorlevel",
    "director": "director",
    "executive": "executive",
}

#: Company size buckets -> the site's ``employerSizes`` codes.
COMPANY_SIZES = {"1-200": 1, "201-500": 2, "501-1000": 3, "1001-5000": 4, "5001+": 5}

#: Job types -> the site's ``jobTypeIndeed`` codes.
JOB_TYPES = {
    "full-time": "CF3CP",
    "part-time": "75GKK",
    "contract": "NJXCK",
    "temporary": "4HKF7",
    "permanent": "5QWDV",
}

#: Search radius options, in miles.
RADII = (0, 5, 10, 15, 25, 50, 100)

MIN_RATINGS = (1, 2, 3, 4)


@dataclass(frozen=True)
class JobFilters:
    """Filters for a job search. ``None`` / ``False`` leaves a filter off.

    Attributes:
        days: Only jobs posted in the last 1, 3, 7, 14 or 30 days.
        sort: ``"relevant"`` (Glassdoor's default order) or ``"newest"``.
        min_salary: Minimum salary (in the currency of the searched location).
        max_salary: Maximum salary.
        min_rating: Minimum company rating: 1, 2, 3 or 4 (stars and up).
        remote: Only remote / work-from-home jobs.
        easy_apply: Only jobs with Glassdoor Easy Apply.
        seniority: ``entry``, ``mid-senior``, ``director`` or ``executive``.
        company_size: ``1-200``, ``201-500``, ``501-1000``, ``1001-5000`` or ``5001+``.
        job_type: ``full-time``, ``part-time``, ``contract``, ``temporary`` or ``permanent``.
        radius: Distance from the location in miles: 0, 5, 10, 15, 25, 50 or 100.
        company_id: Only jobs at this Glassdoor company (employer) ID.
    """

    days: int | None = None
    sort: str | None = None
    min_salary: int | None = None
    max_salary: int | None = None
    min_rating: int | None = None
    remote: bool = False
    easy_apply: bool = False
    seniority: str | None = None
    company_size: str | None = None
    job_type: str | None = None
    radius: int | None = None
    company_id: int | None = None

    def params(self) -> list[tuple[str, str]]:
        """The filters as Glassdoor query parameters. Raises ``ValueError`` on bad values."""
        out: list[tuple[str, str]] = []
        if self.days is not None:
            if int(self.days) not in DATE_POSTED:
                raise ValueError(f"days must be one of {DATE_POSTED}, got {self.days!r}")
            out.append(("fromAge", str(int(self.days))))
        if self.sort is not None:
            if self.sort not in SORTS:
                raise ValueError(f"sort must be one of {tuple(SORTS)}, got {self.sort!r}")
            if SORTS[self.sort]:
                out.append(("sortBy", SORTS[self.sort]))
        if self.min_salary is not None:
            out.append(("minSalary", str(_positive(self.min_salary, "min_salary"))))
        if self.max_salary is not None:
            out.append(("maxSalary", str(_positive(self.max_salary, "max_salary"))))
        if (
            self.min_salary is not None
            and self.max_salary is not None
            and int(self.max_salary) < int(self.min_salary)
        ):
            raise ValueError("max_salary is below min_salary")
        if self.min_rating is not None:
            if int(self.min_rating) not in MIN_RATINGS:
                raise ValueError(
                    f"min_rating must be one of {MIN_RATINGS}, got {self.min_rating!r}"
                )
            out.append(("minRating", f"{int(self.min_rating)}.0"))
        if self.remote:
            out.append(("remoteWorkType", "1"))
        if self.easy_apply:
            out.append(("applicationType", "1"))
        if self.seniority is not None:
            out.append(("seniorityType", _choice(self.seniority, SENIORITY, "seniority")))
        if self.company_size is not None:
            out.append(
                ("employerSizes", str(_choice(self.company_size, COMPANY_SIZES, "company_size")))
            )
        if self.job_type is not None:
            out.append(("jobTypeIndeed", _choice(self.job_type, JOB_TYPES, "job_type")))
        if self.radius is not None:
            if int(self.radius) not in RADII:
                raise ValueError(f"radius must be one of {RADII} (miles), got {self.radius!r}")
            out.append(("radius", str(int(self.radius))))
        if self.company_id is not None:
            out.append(("companyId", str(_positive(self.company_id, "company_id"))))
        return out


def _positive(value: Any, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name} must be a positive number, got {value!r}")
    return number


def _choice(value: str, choices: dict[str, Any], name: str) -> Any:
    key = str(value).strip().lower()
    if key not in choices:
        raise ValueError(f"{name} must be one of {tuple(choices)}, got {value!r}")
    return choices[key]


def absolute(url: str | None) -> str | None:
    """A site-relative Glassdoor link as an absolute URL."""
    if not url:
        return None
    return urljoin(BASE_URL + "/", url)


def location_slug(name: str | None) -> str:
    """``"New York, NY"`` -> ``"new-york-ny"`` (Glassdoor reads the ID, not the slug)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "location"


def keyword_slug(keyword: str) -> str:
    """``"C++ Developer"`` -> ``"c++-developer"``: Glassdoor reads the keyword from it."""
    return "-".join(re.sub(r"[/\\]", " ", keyword).lower().split())


def search_url(
    keyword: str | None = None,
    location_id: int | None = None,
    location_type: str = "C",
    filters: JobFilters | None = None,
    location_name: str | None = None,
) -> str:
    """The job search URL for a keyword and/or a location (by Glassdoor location ID).

    This is Glassdoor's own URL shape, e.g.
    ``/Job/new-york-ny-python-developer-jobs-SRCH_IL.0,11_IC1132348_KO12,28.htm``:
    ``IL``/``KO`` give the position of the location and keyword in the slug, ``IC`` is
    the location type (city) and ID. Filters go in the query string. (The shorter
    ``/Job/jobs.htm?sc.keyword=...`` form redirects here and drops the filters.)
    """
    keyword = " ".join((keyword or "").split())
    if not keyword and location_id is None:
        raise ValueError("give a keyword, a location, or both")
    parts, codes = [], []
    if location_id is not None:
        kind = location_type.upper()
        if kind not in LOCATION_TYPES:
            raise ValueError(f"location type must be one of {tuple(LOCATION_TYPES)}, got {kind!r}")
        place = location_slug(location_name)
        parts.append(place)
        codes.append(f"IL.0,{len(place)}_I{kind}{int(location_id)}")
    if keyword:
        words = keyword_slug(keyword)
        start = len(parts[0]) + 1 if parts else 0
        parts.append(words)
        codes.append(f"KO{start},{start + len(words)}")
    slug = quote("-".join(parts), safe="-")
    url = f"{BASE_URL}/Job/{slug}-jobs-SRCH_{'_'.join(codes)}.htm"
    params = filters.params() if filters is not None else []
    return f"{url}?{urlencode(params)}" if params else url


_JL = re.compile(r"[?&]jl=(\d+)")
_DIGITS = re.compile(r"^\d+$")


def listing_id(value: int | str) -> int:
    """A job listing ID from an ID or a Glassdoor job URL (``...htm?jl=1010288405565``)."""
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if _DIGITS.match(text):
        return int(text)
    match = _JL.search(text)
    if match:
        return int(match.group(1))
    raise ValueError(f"not a Glassdoor job ID or job URL: {value!r}")


def job_url(value: int | str) -> str:
    """The job page for a listing ID (any job URL is normalized to its ID)."""
    return f"{BASE_URL}/job-listing/JV.htm?jl={listing_id(value)}"


_EMPLOYER_IN_URL = re.compile(r"(?:-E|_IE|EI_IE)(\d+)(?:[._]|$)")
_EMPLOYER_CODE = re.compile(r"^E?(\d+)$", re.I)


def employer_id(value: int | str) -> int:
    """A company (employer) ID from an ID, ``E3803`` or any Glassdoor company URL."""
    if isinstance(value, int):
        return value
    text = str(value).strip()
    match = _EMPLOYER_CODE.match(text)
    if match:
        return int(match.group(1))
    if "glassdoor." in text or text.startswith("/"):
        match = _EMPLOYER_IN_URL.search(urlparse(text).path if "://" in text else text)
        if match:
            return int(match.group(1))
    raise ValueError(f"not a Glassdoor company ID or company URL: {value!r}")


def is_company_ref(value: int | str) -> bool:
    """True when ``value`` is a company ID or URL (rather than a name to look up)."""
    try:
        employer_id(value)
    except ValueError:
        return False
    return True


def overview_url(company_id: int) -> str:
    """The company overview page. Glassdoor serves it for any name slug."""
    return f"{BASE_URL}/Overview/Working-at-Company-EI_IE{int(company_id)}.11,18.htm"


_SALARY_PATH = re.compile(r"/Salary/([A-Za-z0-9-]+?)-Salaries-E(\d+)(?:_P\d+)?\.htm")


def salary_path(url: str) -> tuple[str, int] | None:
    """``(name slug, company ID)`` from a company salaries URL, if it is one."""
    match = _SALARY_PATH.search(url)
    return (match.group(1), int(match.group(2))) if match else None


def salaries_url(slug: str, company_id: int, page: int = 1, job_title: str | None = None) -> str:
    """A page of a company's salaries. ``slug`` is the company's name slug
    (``Capgemini`` in ``/Salary/Capgemini-Salaries-E3803.htm``)."""
    if page < 1:
        raise ValueError("page numbers start at 1")
    suffix = f"_P{page}" if page > 1 else ""
    url = f"{BASE_URL}/Salary/{slug}-Salaries-E{int(company_id)}{suffix}.htm"
    if job_title:
        url += "?" + urlencode({"filter.jobTitleFTS": job_title}, quote_via=quote)
    return url


def company_search_url(name: str) -> str:
    """Glassdoor's search page for a company name."""
    return f"{BASE_URL}/Search/results.htm?" + urlencode({"keyword": name.strip()}, quote_via=quote)


def location_lookup_url(term: str) -> str:
    """Glassdoor's location autocomplete (cities, states and countries) for ``term``."""
    params = {"locationTypeFilters": "CITY,STATE,COUNTRY", "caller": "jobs", "term": term.strip()}
    return f"{BASE_URL}/autocomplete/location?" + urlencode(params, quote_via=quote)
