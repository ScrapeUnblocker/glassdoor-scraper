from __future__ import annotations

from glassdoor_scraper.flight import Flight, flight_rows, flight_text

from .pages import Text, flight_html, flight_payload


def test_flight_text_joins_chunks_and_skips_bootstrap() -> None:
    html = flight_html({"1": {"a": 1}, "2": {"b": 2}})
    text = flight_text(html)
    assert text == flight_payload({"1": {"a": 1}, "2": {"b": 2}})


def test_rows_parse_json_and_text_rows_with_multibyte_characters() -> None:
    payload = flight_payload({"1": {"x": "$2"}, "2": Text("café – €5 \U0001f600"), "3": [1, 2, 3]})
    rows = flight_rows(payload)
    assert rows["2"] == "café – €5 \U0001f600"
    assert rows["3"] == [1, 2, 3]


def test_resolve_follows_references_and_paths() -> None:
    flight = Flight(
        flight_html(
            {
                "5": {"props": {"pageProps": {"items": [{"id": 1}, {"id": 2}]}}},
                "6": {"first": "$5:props:pageProps:items:0", "all": "$5:props:pageProps:items"},
                "7": ["$", "$L8", None, {"child": "$6"}],
            }
        )
    )
    holder = flight.first("first")
    assert holder == {"first": {"id": 1}, "all": [{"id": 1}, {"id": 2}]}
    assert flight.follow("$7:props:child:first") == {"id": 1}


def test_escaped_dollars_and_undefined() -> None:
    flight = Flight(flight_html({"1": {"revenue": "$$10+ billion (USD)", "stock": "$undefined"}}))
    assert flight.first("revenue") == {"revenue": "$10+ billion (USD)", "stock": None}


def test_missing_reference_is_left_alone() -> None:
    flight = Flight(flight_html({"1": {"ref": "$ff"}}))
    assert flight.first("ref") == {"ref": "$ff"}


def test_json_value_decodes_text_rows() -> None:
    flight = Flight(flight_html({"1": {"options": "$2"}, "2": Text('[{"name": "fromAge"}]')}))
    holder = next(flight.find("options"))
    assert flight.json_value(holder["options"]) == [{"name": "fromAge"}]


def test_keyed_finds_cache_entries_by_key_prefix() -> None:
    flight = Flight(flight_html({"1": {"fallback": {'#url:"/a",args:#page:2,,': {"n": 1}}}}))
    assert list(flight.keyed('#url:"/a"')) == [('#url:"/a",args:#page:2,,', {"n": 1})]


def test_page_without_payload_is_empty() -> None:
    flight = Flight("<html><body>nothing here</body></html>")
    assert not flight
    assert flight.first("anything") is None
