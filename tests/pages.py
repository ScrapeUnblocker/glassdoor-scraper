"""Small synthetic Glassdoor pages for offline tests.

Real pages are 0.5-2.5 MB; these keep only the shapes the parsers read. A page's data
lives in ``self.__next_f.push([1, "..."])`` chunks: rows of ``<id>:<json>`` or
``<id>:T<hex byte length>,<text>``, pointing at each other with ``"$<id>:<path>"``.
"""

from __future__ import annotations

import json
from typing import Any


class Text(str):
    """A ``T`` (text) row."""


def flight_payload(rows: dict[str, Any]) -> str:
    lines = []
    for key, value in rows.items():
        if isinstance(value, Text):
            lines.append(f"{key}:T{len(value.encode('utf-8')):x},{value}")
        else:
            lines.append(f"{key}:{json.dumps(value, ensure_ascii=False)}\n")
    return "".join(lines)


def flight_html(rows: dict[str, Any], *, title: str = "Glassdoor", body: str = "") -> str:
    """An HTML page whose data payload holds ``rows`` (split over two chunks)."""
    payload = flight_payload(rows)
    middle = len(payload) // 2
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>\n"
        for part in (payload[:middle], payload[middle:])
    )
    return (
        f"<!DOCTYPE html><html><head><title>{title}</title></head>"
        f"<body>{body}\n<script>(self.__next_f=self.__next_f||[]).push([0])</script>\n"
        f"{scripts}</body></html>"
    )


# --------------------------------------------------------------------------- #
# Job search
# --------------------------------------------------------------------------- #


def listing(
    listing_id: int,
    title: str,
    *,
    company: str = "Acme",
    company_id: int = 123,
    rating: float | None = 4.2,
    pay: dict[str, float] | None = None,
    period: str | None = "ANNUAL",
    source: str | None = "EMPLOYER_PROVIDED",
    age: int = 3,
    sponsored: bool = False,
    easy_apply: bool = True,
    awards: bool = False,
) -> dict[str, Any]:
    return {
        "jobview": {
            "header": {
                "ageInDays": age,
                "easyApply": easy_apply,
                "employer": {
                    "bestLedCompanies": [],
                    "bestPlacesToWork": [{"isCurrent": True}] if awards else [],
                    "bestPlacesToWorkCEO": [],
                    "id": company_id,
                    "name": f"{company} Inc.",
                    "ratings": {"overallRating": rating},
                    "shortName": company,
                },
                "employerNameFromSearch": company,
                "goc": "software developer",
                "indeedJobAttribute": {
                    "extractedJobAttributes": [
                        {"key": "X62BT", "value": "Python"},
                        {"key": "FVKX2", "value": "401(k)"},
                        {"key": "CF3CP", "value": "Full-time"},
                    ],
                    "skills": ["X62BT"],
                },
                "isSponsoredJob": sponsored,
                "jobLink": "$44",
                "jobTitleText": title,
                "locId": 1132348,
                "locationName": "New York, NY",
                "locationType": "C",
                "normalizedJobTitle": "software developer",
                "payCurrency": "USD",
                "payPeriod": period if pay else None,
                "payPeriodAdjustedPay": pay,
                "salarySource": source if pay else None,
                "seoJobLink": f"https://www.glassdoor.com/job-listing/x-JV.htm?jl={listing_id}",
            },
            "job": {
                "descriptionFragmentsText": [f"About {title}."],
                "jobTitleText": title,
                "listingId": listing_id,
            },
            "overview": {
                "shortName": company,
                "squareLogoUrl": f"https://media.glassdoor.com/sql/{company_id}/logo.png",
            },
        }
    }


FILTER_OPTIONS = [
    {"type": "DATEPOSTED", "name": "fromAge", "defValue": "-1", "selected": ["7"]},
    {"type": "DISTANCE", "name": "radius", "defValue": "25", "selected": ["25"]},
    {"type": "SORT_BY", "name": "sortBy", "defValue": "", "selected": [""]},
    {"type": "REMOTE_WORK_TYPE", "name": "remoteWorkType", "defValue": 0, "selected": [1]},
]


def search_page(
    listings: list[dict[str, Any]] | None = None,
    *,
    total: int = 2,
    cards: str = "",
) -> str:
    if listings is None:
        listings = [
            listing(
                1001,
                "Python Developer",
                pay={"p10": 60, "p50": 62.5, "p90": 65},
                period="HOURLY",
                sponsored=True,
            ),
            listing(1002, "Data Engineer", company="Globex", company_id=456, rating=0, pay=None),
        ]
    rows = {
        "5": {
            "props": {
                "pageProps": {
                    "jobSearchPage": {
                        "searchResultsData": {
                            "jobListings": {
                                "jobListings": listings,
                                "paginationCursors": [{"cursor": "abc", "pageNumber": 2}],
                                "totalJobsCount": total,
                                "filterOptions": "$43",
                            }
                        },
                        "urlParams": {
                            "locationSeoString": "new york ny",
                            "occupationParam": "python developer",
                        },
                    }
                }
            }
        },
        "43": Text(json.dumps(FILTER_OPTIONS)),
        "4f": [
            "$",
            "$L52",
            None,
            {"initialJobListingsData": "$5:props:pageProps:jobSearchPage:searchResultsData"},
        ],
    }
    title = f"{total} python developer Jobs in New York, NY, October 2026 | Glassdoor"
    return flight_html(rows, title=title, body=cards)


def job_card(
    listing_id: int,
    title: str,
    *,
    company: str = "Lockheed Martin",
    company_id: int = 404,
    rating: str = "4.1",
    salary: str | None = "$88K - $146K <span>(Glassdoor est.)</span>",
    easy_apply: bool = True,
    award: str | None = "Best Places to Work",
) -> str:
    salary_html = (
        f'<div class="JobCard_salaryEstimate__Qp" data-test="detailSalary">{salary}</div>'
        if salary
        else ""
    )
    easy = '<div class="JobCard_easyApplyTag__5v">Easy Apply</div>' if easy_apply else ""
    badge = (
        f'<div aria-label="{award}" class="AwardBadge_awardBadge__dq" data-test="award-badge">'
        f"<span>{award}</span></div>"
        if award
        else ""
    )
    return f"""
<li class="JobsList_jobListItem__wj" data-jobid="{listing_id}" data-test="jobListing">
 <div class="jobCard JobCard_jobCardContent__JQ JobCardWrapper_easyApplyLabelNoWrap__Pt">
  <div class="EmployerProfile_profileContainer__63">
   <img alt="{company} Logo" src="https://media.glassdoor.com/sql/{company_id}/logo.png"/>
   <div class="EmployerProfile_employerNameContainer__pt">
    <span class="EmployerProfile_compactEmployerName__9M">
      {company}
    </span>
    <div aria-valuenow="{rating}" class="rating-single-star_Container__Jb" role="meter">
     <span class="rating-single-star_RatingText__5f">{rating}</span>
    </div>
   </div>
  </div>
  <a class="JobCard_jobTitle__GL" data-test="job-title"
     href="https://www.glassdoor.com/job-listing/x-JV.htm?jl={listing_id}">
    {title}
  </a>
  <div class="JobCard_location__Ds" data-test="emp-location">Uniondale, NY</div>
  {salary_html}
  {badge}
  {easy}
  <div class="JobCard_jobDescriptionSnippet__l1" data-test="descSnippet">
   <div>Build things in a team&hellip;</div>
   <div><b>Skills:</b> Git, Java, Linux</div>
  </div>
  <ul>
   <li><a href="https://www.glassdoor.com/Reviews/Lockheed-Martin-Reviews-E{company_id}.htm">
     Employee reviews</a></li>
  </ul>
 </div>
</li>"""


# --------------------------------------------------------------------------- #
# Job page
# --------------------------------------------------------------------------- #


def job_page(listing_id: int = 1010288405565) -> str:
    details = {
        "companyRatings": {
            "careerOpportunitiesRating": 4.1,
            "ceoRating": 0.81,
            "compensationAndBenefitsRating": 3.8,
            "cultureAndValuesRating": 3.8,
            "overallRating": 4.1,
            "recommendToFriendRating": 0.83,
            "seniorManagementRating": 3.5,
            "workLifeBalanceRating": 4.2,
        },
        "employerId": 404,
        "employerName": "Lockheed Martin",
        "employerOverview": {
            "ceo": {"name": "Jane Doe"},
            "headquarters": "Bethesda, MD",
            "id": 404,
            "name": "Lockheed Martin Corporation",
            "primaryIndustry": {
                "industryName": "Aerospace & Defense",
                "sectorName": "Aerospace & Defense",
            },
            "revenue": "$$10+ billion (USD)",
            "size": "10000+ Employees",
            "squareLogoUrl": "https://media.glassdoor.com/sql/404/logo.png",
            "type": "Company - Public",
            "website": "https://www.lockheedmartin.com",
            "yearFounded": 1995,
        },
        "employerRating": 4.1,
        "expired": False,
        "isEasyApply": False,
        "isSponsoredJob": True,
        "jobDescription": "$22",
        "jobListingDetails": {
            "ageInDays": 6,
            "applyUrl": "/partner/jobListing.htm?pos=101",
            "indeedJobAttribute": {
                "educationLabel": ["Bachelor's degree"],
                "skillsLabel": ["Git", "Python"],
                "yearsOfExperienceLabel": [],
            },
            "jobType": ["Full-time"],
            "remoteWorkTypes": None,
        },
        "jobOverview": {"discoverDate": "2026-10-07T00:00:00", "listingId": listing_id},
        "jobTitle": "Software Engineer - Early Career",
        "listingId": listing_id,
        "location": {"id": 1132443, "name": "Uniondale, NY", "type": "C"},
        "locationName": "Uniondale, NY",
        "map": {
            "country": "United States",
            "lat": 40.70028,
            "lng": -73.59333,
            "postalCode": None,
            "stateName": "New York State",
        },
        "normalizedJobTitle": "software engineer",
        "payCurrency": "USD",
        "payPeriod": "ANNUAL",
        "payPeriodAdjustedPay": {"p10": 88189, "p50": 117176, "p90": 146163},
        "salarySource": "EMPLOYER_PROVIDED",
        "seoJobLink": f"https://www.glassdoor.com/job-listing/x-JV.htm?jl={listing_id}",
        "employerReviewTotalRecords": 2914,
        "employerReviewHighlights": [
            {
                "categoryReviewCount": 453,
                "sentence": "great work life balance",
                "sentiment": "POSITIVE",
            }
        ],
        "employerBenefitsOverview": {"overallBenefitRating": 4.1, "totalBenefitReviews": 2633},
    }
    rows = {
        "20": {"props": {"pageProps": {"jobViewPage": {"jobDetailsData": details}}}},
        "22": Text("<div><p>WHAT WE DO<br>Build – café systems</p><ul><li>Python</li></ul></div>"),
    }
    return flight_html(rows, title="Lockheed Martin hiring Software Engineer | Glassdoor")


# --------------------------------------------------------------------------- #
# Company pages
# --------------------------------------------------------------------------- #


def review(review_id: int, rating: int, title: str) -> dict[str, Any]:
    return {
        "advice": None,
        "cons": "Slow promotions",
        "countHelpful": 2,
        "employerResponses": [{"response": "Thanks for the feedback."}],
        "employmentStatus": "REGULAR",
        "isCurrentJob": True,
        "jobTitle": {"text": "Engineer"},
        "lengthOfEmployment": 3,
        "location": {"name": "Austin, TX"},
        "pros": "Great team",
        "ratingBusinessOutlook": "POSITIVE",
        "ratingCareerOpportunities": 4,
        "ratingCeo": "APPROVE",
        "ratingCompensationAndBenefits": 3,
        "ratingCultureAndValues": 5,
        "ratingDiversityAndInclusion": 5,
        "ratingOverall": rating,
        "ratingRecommendToFriend": "POSITIVE",
        "ratingSeniorLeadership": 4,
        "ratingWorkLifeBalance": 4,
        "reviewDateTime": "2026-10-12T22:03:15.857",
        "reviewId": review_id,
        "summary": title,
    }


def company_page(company_id: int = 123) -> str:
    rows = {
        "10": {
            "employer": {
                "counts": {"salaryCount": 1500},
                "firstNotReassignedEmployerId": company_id,
                "headquarters": "Austin, TX",
                "id": company_id,
                "name": "Acme Corporation",
                "primaryIndustry": {
                    "industryName": "Software",
                    "sectorName": "Information Technology",
                },
                "shortName": "Acme",
                "size": "1001 to 5000 Employees",
                "squareLogoUrl": "https://media.glassdoor.com/sql/123/logo.png",
                "website": "https://acme.example",
            }
        },
        "11": {
            "headquarters": "Austin, TX",
            "id": company_id,
            "overview": {"description": "We make anvils.", "mission": "Anvils for all."},
            "primaryIndustry": {"industryName": "Software"},
            "revenue": "$$100 to $500 million (USD)",
            "shortName": "Acme",
            "size": "1001 to 5000 Employees",
            "stock": "ACME",
            "type": "Company - Public",
            "website": "https://acme.example",
            "yearFounded": 1949,
        },
        "12": {
            "ratings": {
                "businessOutlookRating": 0.81,
                "careerOpportunitiesRating": 4.2,
                "ceoRating": 0.7,
                "compensationAndBenefitsRating": 3.8,
                "cultureAndValuesRating": 4.2,
                "diversityAndInclusionRating": 4.3,
                "overallRating": 4.3,
                "ratedCeo": "$13",
                "recommendToFriendRating": 0.88,
                "reviewCount": 1052,
                "seniorManagementRating": 4,
                "workLifeBalanceRating": 4.2,
            },
            "industryBenchmarkRatings": {"overallRating": 3.63, "ceoRating": 0.72},
            "ratingCountDistribution": {
                "overall": {"_1": 10, "_2": 20, "_3": 30, "_4": 40, "_5": 50},
                "compensationAndBenefits": {"_1": 1, "_2": 2, "_3": 3, "_4": 4, "_5": 5},
                "recommendToFriend": {"RECOMMEND": 90, "WONT_RECOMMEND": 10},
            },
            "reviewsUrl": "/Reviews/Acme-Reviews-E123.htm",
        },
        "13": {"name": "Wile E. Coyote", "title": "CEO"},
        "14": {"reviews": [review(9001, 5, "Great place"), review(9002, 2, "Not for me")]},
        "15": {"reviews": "Reviews"},  # a translation string, not review data
        "16": {
            "awards": [
                {"name": "Best Places to Work &amp; Grow", "year": 2026},
                {"name": "Best Places to Work &amp; Grow", "year": 2026},
                {"name": "Top Employer", "year": None},
            ],
            "locationCount": 12,
        },
        "17": {
            "links": [
                "https://www.glassdoor.com/Overview/Working-at-Company-EI_IE123.11,18.htm",
                "/Overview/Working-at-Acme-EI_IE123.11,15.htm",
                "/Salary/Acme-Salaries-E123.htm",
                "/Jobs/Acme-Jobs-E123.htm",
                "/Interview/Acme-Interview-Questions-E123.htm",
            ]
        },
    }
    return flight_html(rows, title="Working at Acme | Glassdoor")


def salaries_page(company_id: int = 123, page: int = 1, pages: int = 2) -> str:
    key = (
        '#url:"/bff/employer-profile-mono/agg-salary-estimates",args:#sort:"UGC_SALARY_COUNT_DESC",'
        f'sgoc:null,payPeriod:"ANNUAL",pageSize:10,page:{page},jobTitle:"",'
        f"employerId:{company_id},,"
    )

    def stats(base: float) -> dict[str, Any]:
        return {
            "percentiles": [
                {"ident": name, "value": base + step * 10000}
                for step, name in enumerate(("P10", "P25", "P50", "P75", "P90"))
            ]
        }

    results = [
        {
            "basePayStatistics": stats(100000 + page),
            "currency": {"code": "USD"},
            "jobTitle": {"id": 44950 + page, "text": f"Senior Consultant {page}"},
            "mostRecent": "2026-10-07T19:02:47.150",
            "salaryCount": 3038,
            "totalPayStatistics": stats(110000),
        }
    ]
    rows = {
        "7a": {
            "value": {
                "fallback": {
                    key: {
                        "jobTitleCount": 12,
                        "numPages": pages,
                        "queryLocation": {"name": "United States"},
                        "results": results,
                    }
                }
            }
        },
        "8": {
            "employer": {
                "firstNotReassignedEmployerId": company_id,
                "id": company_id,
                "shortName": "Acme",
            }
        },
    }
    return flight_html(rows, title="Acme Salaries | Glassdoor")


def company_search_page() -> str:
    rows = {
        "9": {
            "employerResults": [
                {
                    "employer": {
                        "id": 123,
                        "name": "Acme Corporation",
                        "shortName": "Acme",
                        "squareLogoUrl": "https://media.glassdoor.com/sql/123/logo.png",
                    },
                    "employerRatings": {"overallRating": 4.3},
                }
            ]
        }
    }
    return flight_html(rows, title="acme results | Glassdoor")


LOCATIONS = json.dumps(
    [
        {
            "locationId": 1139761,
            "locationType": "C",
            "locationName": "Austin, TX",
            "longName": "Austin, TX (US)",
            "cityName": "Austin",
            "stateName": "Texas",
            "countryName": "United States",
            "country2LetterIso": "US",
            "label": "Austin, TX",
        },
        {
            "locationId": 1347,
            "locationType": "S",
            "locationName": "Texas",
            "label": "Texas",
            "countryName": "United States",
        },
    ]
)
