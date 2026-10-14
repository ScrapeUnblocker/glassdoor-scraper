"""Turn Glassdoor pages (HTML from the ScrapeUnblocker ``getPageSource`` API) into records.

Each page type is read from where its data actually lives:

* search results - the job list in the page's data payload (30 jobs with salary
  percentiles, age, skills, ...), plus the rendered job cards when "Show more jobs"
  was clicked with browser steps (the extra jobs only exist as cards);
* job pages - the ``jobDetailsData`` object (posting, pay, location, company);
* company overview pages - company details, ratings with the industry benchmark,
  the star distribution and the reviews shown on the page;
* salary pages - the per-job-title pay percentiles;
* the location lookup - a plain JSON list.

All parsers are pure functions of the HTML, so they are easy to test offline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from html import unescape as html_unescape
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .flight import Flight
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
from .urls import BASE_URL, absolute, job_url, overview_url


class GlassdoorError(Exception):
    """Base class for scraper errors."""


class GlassdoorNotFoundError(GlassdoorError, LookupError):
    """Glassdoor has no such job, company or location."""


class GlassdoorParseError(GlassdoorError):
    """The page came back without the data we expected (worth a retry)."""


# --------------------------------------------------------------------------- #
# Small value helpers
# --------------------------------------------------------------------------- #

_SALARY_SOURCES = {"EMPLOYER_PROVIDED": "employer", "ESTIMATED": "estimate"}
_AWARDS = (
    ("bestPlacesToWork", "Best Places to Work"),
    ("bestPlacesToWorkCEO", "Best CEO"),
    ("bestLedCompanies", "Best-Led Companies"),
)
_BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rating(value: Any) -> float | None:
    """A 1-5 star rating; Glassdoor uses 0 for "not rated"."""
    number = _float(value)
    return number if number else None


def _pct(value: Any) -> int | None:
    """A 0-1 share (0.88) as a percentage (88)."""
    number = _float(value)
    return None if number is None else int(round(number * 100))


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [item.strip() for item in _list(value) if isinstance(item, str) and item.strip()]


def _date(value: Any) -> str | None:
    """``"2026-10-12T22:03:15.857"`` -> ``"2026-10-12"``."""
    text = _text(value)
    return text[:10] if text and re.match(r"\d{4}-\d{2}-\d{2}", text) else None


def posted_date(age_days: int | None, today: dt.date | None = None) -> str | None:
    """The posting date implied by "posted N days ago"."""
    if age_days is None:
        return None
    return ((today or dt.date.today()) - dt.timedelta(days=age_days)).isoformat()


def node_text(node: Tag | None) -> str:
    """The text of an element: ``<br>`` and blocks become line breaks, other
    whitespace collapses (the API may return pretty-printed HTML)."""
    if node is None:
        return ""
    chunks: list[str] = []

    def walk(element: Tag) -> None:
        for child in element.children:
            if isinstance(child, NavigableString):
                chunks.append(re.sub(r"\s+", " ", str(child)))
            elif isinstance(child, Tag):
                if child.name == "br":
                    chunks.append("\n")
                    continue
                block = child.name in _BLOCK_TAGS
                if block:
                    chunks.append("\n")
                if child.name == "li":
                    chunks.append("- ")
                walk(child)
                if block:
                    chunks.append("\n")

    walk(node)
    lines = [" ".join(line.split()) for line in "".join(chunks).split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(html: str | None) -> str | None:
    """Readable plain text from a fragment of HTML (a job description)."""
    if not html:
        return None
    return node_text(BeautifulSoup(html, "html.parser")) or None


# --------------------------------------------------------------------------- #
# Salaries
# --------------------------------------------------------------------------- #

_CURRENCY_SYMBOLS = (
    ("CA$", "CAD"),
    ("A$", "AUD"),
    ("NZ$", "NZD"),
    ("S$", "SGD"),
    ("HK$", "HKD"),
    ("R$", "BRL"),
    ("MX$", "MXN"),
    ("$", "USD"),
    ("£", "GBP"),
    ("€", "EUR"),
    ("₹", "INR"),
    ("¥", "JPY"),
    ("CHF", "CHF"),
)
_PERIODS = (
    ("per hour", "hourly"),
    ("per day", "daily"),
    ("per week", "weekly"),
    ("per month", "monthly"),
    ("per year", "annual"),
)
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?(?![\w])")


def parse_salary_text(text: str | None) -> dict[str, Any]:
    """Read a salary as a job card prints it.

    ``"$88K - $146K (Employer provided)"`` ->
    ``{"min": 88000.0, "max": 146000.0, "currency": "USD", "period": "annual",
    "source": "employer"}``. Unknown parts are ``None``.
    """
    out: dict[str, Any] = {
        "min": None,
        "max": None,
        "currency": None,
        "period": None,
        "source": None,
    }
    if not text:
        return out
    clean = " ".join(text.split())
    lower = clean.lower()
    if "employer provided" in lower:
        out["source"] = "employer"
    elif "est." in lower or "estimate" in lower:
        out["source"] = "estimate"
    pay = re.split(r"\(", clean, maxsplit=1)[0]
    amounts = []
    for number, suffix in _AMOUNT.findall(pay):
        value = float(number.replace(",", ""))
        value *= {"k": 1_000, "m": 1_000_000}.get(suffix.lower(), 1) if suffix else 1
        amounts.append(value)
    if not amounts:
        return out
    out["min"], out["max"] = amounts[0], amounts[-1]
    for symbol, code in _CURRENCY_SYMBOLS:
        if symbol in pay:
            out["currency"] = code
            break
    out["period"] = next((name for marker, name in _PERIODS if marker in lower), "annual")
    return out


def _pay(holder: dict[str, Any]) -> dict[str, Any]:
    """Salary fields from a job object (``payPeriodAdjustedPay`` percentiles)."""
    pay = _dict(holder.get("payPeriodAdjustedPay"))
    low, mid, high = _float(pay.get("p10")), _float(pay.get("p50")), _float(pay.get("p90"))
    if low is None and mid is None and high is None:
        return {
            "salary_min": None,
            "salary_median": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "salary_source": None,
        }
    period = _text(holder.get("payPeriod"))
    source = _text(holder.get("salarySource"))
    return {
        "salary_min": low,
        "salary_median": mid,
        "salary_max": high,
        "salary_currency": _text(holder.get("payCurrency")),
        "salary_period": period.lower() if period else None,
        "salary_source": _SALARY_SOURCES.get(source or "", source.lower() if source else None),
    }


# --------------------------------------------------------------------------- #
# Job search
# --------------------------------------------------------------------------- #


def _awards(employer: dict[str, Any]) -> list[str]:
    return [label for key, label in _AWARDS if _list(employer.get(key))]


def job_from_listing(item: dict[str, Any], today: dt.date | None = None) -> Job | None:
    """One job from the search payload (``jobListings[i]``)."""
    view = _dict(item.get("jobview"))
    header, job, overview = (
        _dict(view.get("header")),
        _dict(view.get("job")),
        _dict(view.get("overview")),
    )
    listing = _int(job.get("listingId"))
    title = _text(job.get("jobTitleText")) or _text(header.get("jobTitleText"))
    if listing is None or not title:
        return None
    employer = _dict(header.get("employer"))
    attributes = _dict(header.get("indeedJobAttribute"))
    skill_keys = set(_strings(attributes.get("skills")))
    skills, tags = [], []
    for attribute in _list(attributes.get("extractedJobAttributes")):
        value = _text(_dict(attribute).get("value"))
        if value:
            (skills if _dict(attribute).get("key") in skill_keys else tags).append(value)
    age = _int(header.get("ageInDays"))
    fragments = _strings(job.get("descriptionFragmentsText"))
    return Job(
        listing_id=listing,
        title=title,
        company=_text(employer.get("shortName"))
        or _text(header.get("employerNameFromSearch"))
        or _text(overview.get("shortName")),
        company_id=_int(employer.get("id")),
        company_rating=_rating(_dict(employer.get("ratings")).get("overallRating")),
        location=_text(header.get("locationName")),
        location_id=_int(header.get("locId")),
        **_pay(header),
        age_days=age,
        posted_date=posted_date(age, today),
        easy_apply=header.get("easyApply") if isinstance(header.get("easyApply"), bool) else None,
        sponsored=header.get("isSponsoredJob")
        if isinstance(header.get("isSponsoredJob"), bool)
        else None,
        occupation=_text(header.get("normalizedJobTitle")) or _text(header.get("goc")),
        skills=skills,
        tags=tags,
        awards=_awards(employer),
        snippet=" ".join(fragments) or None,
        logo=_text(overview.get("squareLogoUrl")),
        url=_text(header.get("seoJobLink")) or job_url(listing),
    )


def _employer_from_links(card: Tag) -> int | None:
    for link in card.select("a[href]"):
        match = re.search(
            r"/(?:Reviews|Salary|Overview|Interview)/[^\"]*?-E(?:I_IE)?(\d+)[._]",
            link.get("href", ""),
        )
        if match:
            return int(match.group(1))
    return None


def job_from_card(card: Tag) -> Job | None:
    """One job from a rendered job card (``li[data-test=jobListing]``)."""
    listing = _int(card.get("data-jobid"))
    title_link = card.select_one('[data-test="job-title"]')
    title = node_text(title_link) if title_link else ""
    if listing is None or not title:
        return None
    name = next(
        (
            tag
            for tag in card.select('[class*="EmployerName"], [class*="employerName"]')
            if "Container" not in " ".join(tag.get("class") or [])
        ),
        None,
    )
    rating = card.select_one('[role="meter"][aria-valuenow], [class*="RatingText"]')
    rating_value = None
    if rating is not None:
        rating_value = _rating(rating.get("aria-valuenow") or node_text(rating))
    salary_node = card.select_one('[data-test="detailSalary"]')
    salary = parse_salary_text(node_text(salary_node) if salary_node else None)
    snippet_box = card.select_one('[data-test="descSnippet"]')
    snippet, skills = None, []
    if snippet_box is not None:
        for block in snippet_box.find_all("div", recursive=False) or [snippet_box]:
            text = node_text(block)
            if text.lower().startswith("skills:"):
                skills = [s.strip() for s in text.split(":", 1)[1].split(",") if s.strip()]
            elif text and snippet is None:
                snippet = re.sub(r"(?:…|&hellip;|\.\.\.)$", "", text).strip() or None
    logo = card.select_one('img[src*="media.glassdoor.com"]') or card.select_one("img[src]")
    awards = []
    for badge in card.select('[data-test="award-badge"]'):
        label = badge.get("aria-label") or node_text(badge)
        if label and label not in awards:
            awards.append(label)
    easy_apply = any(
        node_text(tag).lower() == "easy apply" for tag in card.select('[class*="easyApply"]')
    )
    return Job(
        listing_id=listing,
        title=title,
        company=(node_text(name) or None) if name is not None else None,
        company_id=_employer_from_links(card),
        company_rating=rating_value,
        location=node_text(card.select_one('[data-test="emp-location"]')) or None,
        salary_min=salary["min"],
        salary_max=salary["max"],
        salary_currency=salary["currency"],
        salary_period=salary["period"],
        salary_source=salary["source"],
        easy_apply=easy_apply,
        skills=skills,
        awards=awards,
        snippet=snippet,
        logo=logo.get("src") if logo is not None else None,
        url=absolute(title_link.get("href")) if title_link is not None else job_url(listing),
    )


def parse_job_cards(html: str) -> list[Job]:
    """The rendered job cards of a search page (present after browser steps ran)."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select('li[data-test="jobListing"][data-jobid]'):
        job = job_from_card(card)
        if job is not None:
            jobs.append(job)
    return jobs


def _merge(rich: Job, card: Job) -> Job:
    """A payload job, with anything only the card shows filled in."""
    for name in ("awards", "skills"):
        if not getattr(rich, name) and getattr(card, name):
            setattr(rich, name, getattr(card, name))
    for name in ("company_rating", "logo", "company_id", "snippet"):
        if getattr(rich, name) is None and getattr(card, name) is not None:
            setattr(rich, name, getattr(card, name))
    return rich


def _applied_filters(flight: Flight, options: Any) -> dict[str, Any]:
    """The filters Glassdoor says it applied (anything not at its default)."""
    applied: dict[str, Any] = {}
    for option in _list(flight.json_value(options)):
        option = _dict(option)
        name, selected = option.get("name"), _list(option.get("selected"))
        if not name or not selected:
            continue
        default = option.get("defValue")
        if [str(value) for value in selected] == [str(default)]:
            continue
        values = [str(value) for value in selected]
        applied[str(name)] = values[0] if len(values) == 1 else values
    return applied


def parse_search_page(
    html: str,
    url: str,
    *,
    pages_requested: int = 1,
    location: str | None = None,
    today: dt.date | None = None,
) -> JobSearchPage:
    """A job search page: jobs, total count and the filters Glassdoor applied."""
    flight = Flight(html)
    holder = None
    for candidate in flight.find("jobListings"):
        if isinstance(candidate.get("jobListings"), list) or (
            isinstance(candidate.get("jobListings"), str) and "totalJobsCount" in candidate
        ):
            holder = flight.resolve(candidate)
            break
    if holder is None:
        raise GlassdoorParseError("no job search results in the page")

    rich: dict[int, Job] = {}
    for item in _list(holder.get("jobListings")):
        job = job_from_listing(_dict(item), today)
        if job is not None and job.listing_id not in rich:
            rich[job.listing_id] = job

    jobs: list[Job] = []
    seen: set[int] = set()
    cards = parse_job_cards(html) if "data-jobid" in html else []
    for card in cards:
        if card.listing_id in seen:
            continue
        seen.add(card.listing_id)
        jobs.append(_merge(rich[card.listing_id], card) if card.listing_id in rich else card)
    for listing, job in rich.items():  # a plain fetch has no rendered cards
        if listing not in seen:
            seen.add(listing)
            jobs.append(job)

    params = _dict(flight.first("urlParams") or {}).get("urlParams")
    params = _dict(params)
    total = _int(holder.get("totalJobsCount"))
    loaded = max(1, -(-len(jobs) // 30)) if jobs else 1
    expected = pages_requested
    if total is not None:
        expected = min(pages_requested, max(1, -(-total // 30)))
    return JobSearchPage(
        url=url,
        keyword=_text(params.get("occupationParam")) or _text(params.get("keyword")),
        location=location or _location_label(html),
        total=total,
        pages_loaded=loaded,
        complete=loaded >= expected or (total is not None and len(jobs) >= total),
        filters=_applied_filters(flight, holder.get("filterOptions")),
        jobs=jobs,
    )


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TITLE_LOCATION = re.compile(r"\bjobs in (.+?)(?:, [A-Z][a-z]+ \d{4})?(?: - [^|]*)?\s*\|", re.I)


def _location_label(html: str) -> str | None:
    """The searched location as the page title names it ("New York, NY")."""
    title = _TITLE.search(html)
    match = _TITLE_LOCATION.search(html_unescape(title.group(1))) if title else None
    return match.group(1).strip() if match else None


# --------------------------------------------------------------------------- #
# Job pages
# --------------------------------------------------------------------------- #


def parse_ratings(data: Any, review_count: Any = None) -> Ratings | None:
    """A ratings object (``overallRating``, ``ceoRating``, ...) as :class:`Ratings`."""
    data = _dict(data)
    if not data:
        return None
    ceo = _dict(data.get("ratedCeo"))
    return Ratings(
        overall=_rating(data.get("overallRating")),
        career_opportunities=_rating(data.get("careerOpportunitiesRating")),
        compensation_benefits=_rating(data.get("compensationAndBenefitsRating")),
        culture_values=_rating(data.get("cultureAndValuesRating")),
        diversity_inclusion=_rating(data.get("diversityAndInclusionRating")),
        senior_management=_rating(data.get("seniorManagementRating")),
        work_life_balance=_rating(data.get("workLifeBalanceRating")),
        recommend_to_friend_pct=_pct(data.get("recommendToFriendRating")),
        ceo_approval_pct=_pct(data.get("ceoRating")),
        positive_outlook_pct=_pct(data.get("businessOutlookRating")),
        review_count=_int(data.get("reviewCount") if review_count is None else review_count),
        ceo_name=_text(ceo.get("name")),
    )


def parse_job_page(html: str, url: str, *, today: dt.date | None = None) -> JobDetails:
    """A job page: the full posting, pay, location and company summary."""
    flight = Flight(html)
    holder = flight.first("jobDetailsData")
    data = _dict(holder.get("jobDetailsData")) if holder else {}
    if not data:
        raise GlassdoorParseError("no job details in the page")
    details = _dict(data.get("jobListingDetails"))
    overview = _dict(data.get("jobOverview"))
    employer = _dict(data.get("employerOverview"))
    industry = _dict(employer.get("primaryIndustry"))
    attributes = _dict(details.get("indeedJobAttribute"))
    place = _dict(data.get("map"))
    listing = _int(data.get("listingId")) or _int(overview.get("listingId"))
    title = _text(data.get("jobTitle")) or _text(details.get("jobTitleText"))
    if listing is None or not title:
        raise GlassdoorParseError("job details without an ID or title")
    age = _int(details.get("ageInDays"))
    description_html = _text(data.get("jobDescription")) or _text(overview.get("description"))
    benefits = _dict(data.get("employerBenefitsOverview"))
    highlights = []
    for item in _list(data.get("employerReviewHighlights")):
        item = _dict(item)
        sentence = _text(item.get("sentence"))
        if sentence:
            highlights.append(
                ReviewHighlight(
                    sentence=sentence,
                    sentiment=_text(item.get("sentiment")),
                    review_count=_int(item.get("categoryReviewCount")),
                )
            )
    pay = _pay(data) if _dict(data.get("payPeriodAdjustedPay")) else _pay(details)
    ratings = parse_ratings(data.get("companyRatings") or employer.get("ratings"))
    if ratings is not None and ratings.ceo_name is None:
        ratings.ceo_name = _text(_dict(employer.get("ceo")).get("name"))
    return JobDetails(
        listing_id=listing,
        title=title,
        company=_text(data.get("employerName")) or _text(details.get("employerNameFromSearch")),
        company_id=_int(data.get("employerId")),
        company_rating=_rating(data.get("employerRating")),
        location=_text(data.get("locationName")) or _text(details.get("locationName")),
        location_id=_int(_dict(data.get("location")).get("id")) or _int(details.get("locId")),
        region=_text(place.get("stateName")),
        country=_text(place.get("country")),
        postal_code=_text(place.get("postalCode")),
        latitude=_float(place.get("lat")),
        longitude=_float(place.get("lng")),
        **pay,
        job_types=_strings(details.get("jobType")),
        remote=_strings(details.get("remoteWorkTypes")),
        education=_strings(attributes.get("educationLabel")),
        experience=_strings(attributes.get("yearsOfExperienceLabel")),
        skills=_strings(attributes.get("skillsLabel")),
        age_days=age,
        posted_date=_date(overview.get("discoverDate")) or posted_date(age, today),
        easy_apply=data.get("isEasyApply") if isinstance(data.get("isEasyApply"), bool) else None,
        sponsored=data.get("isSponsoredJob")
        if isinstance(data.get("isSponsoredJob"), bool)
        else None,
        expired=data.get("expired") if isinstance(data.get("expired"), bool) else None,
        occupation=_text(data.get("normalizedJobTitle")) or _text(details.get("goc")),
        description=html_to_text(description_html),
        description_html=description_html,
        company_legal_name=_text(employer.get("name")),
        company_headquarters=_text(employer.get("headquarters")),
        company_size=_text(employer.get("size")),
        company_revenue=_text(employer.get("revenue")),
        company_type=_text(employer.get("type")),
        company_industry=_text(industry.get("industryName")),
        company_sector=_text(industry.get("sectorName")),
        company_founded=_int(employer.get("yearFounded")),
        company_website=_text(employer.get("website")),
        company_logo=_text(employer.get("squareLogoUrl")) or _text(data.get("employerSquareLogo")),
        company_ratings=ratings,
        company_review_count=_int(data.get("employerReviewTotalRecords")),
        review_highlights=highlights,
        benefits_rating=_rating(benefits.get("overallBenefitRating")),
        benefits_review_count=_int(benefits.get("totalBenefitReviews")),
        url=_text(data.get("seoJobLink")) or _text(details.get("seoJobLink")) or url,
    )


# --------------------------------------------------------------------------- #
# Company pages
# --------------------------------------------------------------------------- #

_LINK_KINDS = {
    "url": r"/Overview/Working-at-[A-Za-z0-9-]+-EI_IE{id}\.\d+,\d+\.htm",
    "reviews_url": r"/Reviews/[A-Za-z0-9-]+-Reviews-E{id}\.htm",
    "salaries_url": r"/Salary/[A-Za-z0-9-]+-Salaries-E{id}\.htm",
    "jobs_url": r"/Jobs/[A-Za-z0-9-]+-Jobs-E{id}\.htm",
    "interviews_url": r"/Interview/[A-Za-z0-9-]+-Interview-Questions-E{id}\.htm",
}


def parse_review(data: dict[str, Any]) -> Review | None:
    """One review object as :class:`Review`."""
    review = _int(data.get("reviewId"))
    if review is None:
        return None
    responses = [
        _text(_dict(item).get("response")) for item in _list(data.get("employerResponses"))
    ]
    return Review(
        review_id=review,
        date=_date(data.get("reviewDateTime")),
        title=_text(data.get("summary")),
        rating=_rating(data.get("ratingOverall")),
        pros=_text(data.get("pros")),
        cons=_text(data.get("cons")),
        advice=_text(data.get("advice")),
        job_title=_text(_dict(data.get("jobTitle")).get("text")),
        location=_text(_dict(data.get("location")).get("name")),
        employment_status=_text(data.get("employmentStatus")),
        current_employee=data.get("isCurrentJob")
        if isinstance(data.get("isCurrentJob"), bool)
        else None,
        years_employed=_int(data.get("lengthOfEmployment")),
        recommends=_text(data.get("ratingRecommendToFriend")),
        ceo_opinion=_text(data.get("ratingCeo")),
        business_outlook=_text(data.get("ratingBusinessOutlook")),
        career_opportunities=_rating(data.get("ratingCareerOpportunities")),
        compensation_benefits=_rating(data.get("ratingCompensationAndBenefits")),
        culture_values=_rating(data.get("ratingCultureAndValues")),
        diversity_inclusion=_rating(data.get("ratingDiversityAndInclusion")),
        senior_management=_rating(data.get("ratingSeniorLeadership")),
        work_life_balance=_rating(data.get("ratingWorkLifeBalance")),
        helpful_count=_int(data.get("countHelpful")),
        employer_response=next((text for text in responses if text), None),
    )


def _distribution(data: Any) -> dict[str, dict[str, int]]:
    """``{"overall": {"_1": 1336, ...}}`` -> ``{"overall": {"1": 1336, ...}}``."""
    out: dict[str, dict[str, int]] = {}
    for category, counts in _dict(data).items():
        row = {
            str(key).lstrip("_").lower(): count
            for key, count in _dict(counts).items()
            if isinstance(count, int)
        }
        if row:
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", str(category)).lower().replace("_and_", "_")
            out[name] = row
    return out


def _site_links(flight: Flight, company: int) -> dict[str, str | None]:
    links: dict[str, str | None] = {}
    generic = urlparse(overview_url(company)).path
    for name, pattern in _LINK_KINDS.items():
        found = (m.group(0) for m in re.finditer(pattern.format(id=company), flight.text))
        links[name] = absolute(next((path for path in found if path != generic), None))
    return links


def _same_company(data: dict[str, Any], company: int | None) -> bool:
    return company is None or _int(data.get("id")) == company


def parse_company_page(html: str, url: str, company_id: int | None = None) -> Company:
    """A company overview page: details, ratings, distribution and reviews."""
    flight = Flight(html)
    details: dict[str, Any] = {}
    for found in flight.find("yearFounded"):
        found = flight.resolve(found)
        if "headquarters" in found and _same_company(found, company_id):
            details = found
            break
    basic: dict[str, Any] = {}
    for found in flight.find("firstNotReassignedEmployerId"):
        found = flight.resolve(found)
        if _same_company(found, company_id):
            basic = found
            break
    if not details and not basic:
        raise GlassdoorParseError("no company profile in the page")
    company = _int(details.get("id")) or _int(basic.get("id")) or company_id
    if company is None:
        raise GlassdoorParseError("company profile without an ID")

    summary = _dict(flight.first("ratingCountDistribution"))
    review_total = None
    reviews: list[Review] = []
    seen: set[int] = set()
    for holder in flight.find("reviews"):
        items = flight.resolve(holder.get("reviews"))
        if not any(isinstance(item, dict) and "reviewId" in item for item in _list(items)):
            continue
        for item in _list(items):
            review = parse_review(_dict(item))
            if review is not None and review.review_id not in seen:
                seen.add(review.review_id)
                reviews.append(review)
    for holder in flight.find("reviewsCount"):
        review_total = _int(holder.get("reviewsCount"))
        break

    awards = []
    for holder in flight.find("awards"):
        for award in _list(flight.resolve(holder.get("awards"))):
            award = _dict(award)
            name = _text(html_unescape(award.get("name") or ""))
            if name:
                year = _int(award.get("year"))
                label = f"{name} ({year})" if year else name
                if label not in awards:
                    awards.append(label)
        if awards:
            break
    office_locations = None
    for holder in flight.find("locationCount"):
        office_locations = _int(holder.get("locationCount"))
        break

    industry = _dict(details.get("primaryIndustry")) or _dict(basic.get("primaryIndustry"))
    sector = _text(industry.get("sectorName")) or _text(
        _dict(basic.get("primaryIndustry")).get("sectorName")
    )
    overview = _dict(details.get("overview")) or _dict(basic.get("overview"))
    ratings = parse_ratings(summary.get("ratings"))
    if ratings is not None and ratings.review_count is None:
        ratings.review_count = review_total
    links = _site_links(flight, company)
    links["url"] = links["url"] or url
    if summary.get("reviewsUrl") and not links["reviews_url"]:
        links["reviews_url"] = absolute(summary["reviewsUrl"])
    return Company(
        id=company,
        name=_text(details.get("shortName")) or _text(basic.get("shortName")),
        legal_name=_text(basic.get("name")),
        website=_text(details.get("website")) or _text(basic.get("website")),
        headquarters=_text(details.get("headquarters")) or _text(basic.get("headquarters")),
        size=_text(details.get("size")) or _text(basic.get("size")),
        founded=_int(details.get("yearFounded")),
        revenue=_text(details.get("revenue")),
        type=_text(details.get("type")),
        industry=_text(industry.get("industryName")),
        sector=sector,
        stock=_text(details.get("stock")),
        description=_text(overview.get("description")),
        mission=_text(overview.get("mission")),
        logo=_text(basic.get("squareLogoUrl")),
        office_locations=office_locations,
        salary_count=_int(_dict(basic.get("counts")).get("salaryCount")),
        awards=awards,
        ratings=ratings,
        industry_ratings=parse_ratings(summary.get("industryBenchmarkRatings")),
        rating_distribution=_distribution(summary.get("ratingCountDistribution")),
        reviews=reviews,
        **links,
    )


def parse_company_search(html: str) -> list[CompanyMatch]:
    """Companies on Glassdoor's search page for a name (best match first)."""
    flight = Flight(html)
    holder = flight.first("employerResults")
    matches = []
    for item in _list(_dict(holder).get("employerResults")):
        employer = _dict(_dict(item).get("employer"))
        company = _int(employer.get("id"))
        if company is None:
            continue
        matches.append(
            CompanyMatch(
                id=company,
                name=_text(employer.get("shortName")) or _text(employer.get("name")),
                legal_name=_text(employer.get("name")),
                rating=_rating(_dict(_dict(item).get("employerRatings")).get("overallRating")),
                logo=_text(employer.get("squareLogoUrl")),
            )
        )
    return matches


# --------------------------------------------------------------------------- #
# Salaries
# --------------------------------------------------------------------------- #

_SALARY_KEY = '#url:"/bff/employer-profile-mono/agg-salary-estimates"'


def _percentiles(stats: Any) -> dict[str, float | None]:
    values = {
        _text(_dict(item).get("ident")): _float(_dict(item).get("value"))
        for item in _list(_dict(stats).get("percentiles"))
    }
    return {name: values.get(name) for name in ("P10", "P25", "P50", "P75", "P90")}


def parse_salaries_page(html: str, url: str, company_id: int, page: int = 1) -> SalaryPage:
    """One page of a company's salaries (pay percentiles per job title)."""
    flight = Flight(html)
    data: dict[str, Any] = {}
    query = ""
    for key, value in flight.keyed(_SALARY_KEY):
        if f"employerId:{company_id}," in key or not data:
            data, query = _dict(flight.resolve(value)), key
            if f"employerId:{company_id}," in key:
                break
    if not data or not isinstance(data.get("results"), list):
        raise GlassdoorParseError("no salaries in the page")
    period = re.search(r'payPeriod:"(\w+)"', query)
    page_number = re.search(r"\bpage:(\d+)", query)
    company = None
    for found in flight.find("firstNotReassignedEmployerId"):
        found = flight.resolve(found)
        if _same_company(found, company_id):
            company = _text(found.get("shortName")) or _text(found.get("name"))
            break
    salaries = []
    for item in data["results"]:
        item = _dict(item)
        title = _dict(item.get("jobTitle"))
        name = _text(title.get("text"))
        if not name:
            continue
        base, total = (
            _percentiles(item.get("basePayStatistics")),
            _percentiles(item.get("totalPayStatistics")),
        )
        salaries.append(
            Salary(
                job_title=name,
                job_title_id=_int(title.get("id")),
                salary_count=_int(item.get("salaryCount")),
                currency=_text(_dict(item.get("currency")).get("code")),
                pay_period=period.group(1).lower() if period else None,
                base_p10=base["P10"],
                base_p25=base["P25"],
                base_median=base["P50"],
                base_p75=base["P75"],
                base_p90=base["P90"],
                total_p10=total["P10"],
                total_p25=total["P25"],
                total_median=total["P50"],
                total_p75=total["P75"],
                total_p90=total["P90"],
                last_reported=_date(item.get("mostRecent")),
            )
        )
    return SalaryPage(
        url=url,
        company_id=company_id,
        company=company,
        page=int(page_number.group(1)) if page_number else page,
        pages=_int(data.get("numPages")),
        job_title_count=_int(data.get("jobTitleCount")),
        location=_text(_dict(data.get("queryLocation")).get("name")),
        salaries=salaries,
    )


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #


def _json_in(text: str) -> Any:
    """The JSON document in a response (bare, or wrapped in an HTML ``<pre>``)."""
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise GlassdoorParseError("no JSON in the response")
    try:
        return json.JSONDecoder().raw_decode(text, start)[0]
    except ValueError:
        soup = BeautifulSoup(text, "html.parser")
        try:
            return json.loads(soup.get_text())
        except ValueError as exc:
            raise GlassdoorParseError("the response is not valid JSON") from exc


def parse_locations(text: str) -> list[Location]:
    """The location lookup response: cities, states and countries."""
    data = _json_in(text)
    if isinstance(data, dict) and data.get("status"):
        raise GlassdoorParseError(f"location lookup failed: {data.get('message') or data}")
    locations = []
    for item in _list(data):
        item = _dict(item)
        location = _int(item.get("locationId") or item.get("id"))
        kind = _text(item.get("locationType"))
        name = _text(item.get("label")) or _text(item.get("locationName"))
        if location is None or not kind or not name:
            continue
        locations.append(
            Location(
                id=location,
                type=kind,
                name=name,
                long_name=_text(item.get("longName")),
                city=_text(item.get("cityName")),
                state=_text(item.get("stateName")),
                country=_text(item.get("countryName")),
                country_code=_text(item.get("country2LetterIso")),
            )
        )
    return locations


__all__ = [
    "BASE_URL",
    "GlassdoorError",
    "GlassdoorNotFoundError",
    "GlassdoorParseError",
    "html_to_text",
    "job_from_card",
    "job_from_listing",
    "parse_company_page",
    "parse_company_search",
    "parse_job_cards",
    "parse_job_page",
    "parse_locations",
    "parse_ratings",
    "parse_review",
    "parse_salaries_page",
    "parse_salary_text",
    "parse_search_page",
    "posted_date",
]
