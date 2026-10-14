"""Read the React Server Components payload Glassdoor pages ship with.

Glassdoor is a Next.js app. Every page carries its data in ``self.__next_f.push``
script chunks: a list of rows (``<id>:<json>`` or ``<id>:T<hex length>,<text>``) that
point at each other with ``"$<id>"`` / ``"$<id>:<path>"`` references. These helpers
join the chunks, split the rows and follow the references, so the parsers can work
with plain Python dicts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

_FLIGHT_MARK = "self.__next_f.push([1,"
_ROW_ID = re.compile(r"([0-9a-f]+):")
_REF = re.compile(r"^\$L?([0-9a-f]+)(?::(.+))?$")
_ELEMENT_KEYS = {"type": 1, "key": 2, "props": 3}
_MAX_DEPTH = 60


def flight_text(html: str) -> str:
    """The payload of a page: every ``self.__next_f.push([1, "..."])`` chunk, joined."""
    decoder = json.JSONDecoder()
    chunks: list[str] = []
    start = html.find(_FLIGHT_MARK)
    while start != -1:
        try:
            chunk, end = decoder.raw_decode(html, start + len(_FLIGHT_MARK))
        except ValueError:
            start = html.find(_FLIGHT_MARK, start + 1)
            continue
        if isinstance(chunk, str):
            chunks.append(chunk)
        start = html.find(_FLIGHT_MARK, end)
    return "".join(chunks)


def _skip_utf8(text: str, start: int, size: int) -> int:
    """The index ``size`` UTF-8 bytes after ``start`` (text rows count bytes)."""
    position, counted = start, 0
    while counted < size and position < len(text):
        counted += len(text[position].encode("utf-8"))
        position += 1
    return position


def flight_rows(payload: str) -> dict[str, Any]:
    """Split a payload into its rows: ``{row id: value}``."""
    decoder = json.JSONDecoder()
    rows: dict[str, Any] = {}
    position, size = 0, len(payload)
    while position < size:
        if payload[position] == "\n":
            position += 1
            continue
        match = _ROW_ID.match(payload, position)
        if match:
            key, position = match.group(1), match.end()
            if payload.startswith("T", position):  # T<hex byte length>,<text>
                comma = payload.find(",", position)
                try:
                    length = int(payload[position + 1 : comma], 16)
                except ValueError:
                    length = -1
                if comma != -1 and length >= 0:
                    end = _skip_utf8(payload, comma + 1, length)
                    rows[key] = payload[comma + 1 : end]
                    position = end
                    continue
            while position < size and payload[position].isupper():  # I[...], HL[...]
                position += 1
            try:
                rows[key], position = decoder.raw_decode(payload, position)
                continue
            except ValueError:
                pass
        newline = payload.find("\n", position)
        if newline == -1:
            break
        position = newline + 1
    return rows


class Flight:
    """The rows of one page, with reference resolution and search helpers."""

    def __init__(self, html: str) -> None:
        self.text = flight_text(html)
        self.rows = flight_rows(self.text) if self.text else {}

    def __bool__(self) -> bool:
        return bool(self.rows)

    def follow(self, value: Any, depth: int = 0) -> Any:
        """Follow a ``$<row>`` / ``$L<row>`` / ``$<row>:<path>`` reference."""
        if depth > _MAX_DEPTH or not isinstance(value, str):
            return value
        if value.startswith("$$"):  # an escaped literal "$" ("$$10+ billion" is "$10+ billion")
            return value[1:]
        match = _REF.match(value)
        if not match or match.group(1) not in self.rows:
            return None if value == "$undefined" else value
        target = self.follow(self.rows[match.group(1)], depth + 1)
        for key in match.group(2).split(":") if match.group(2) else []:
            target = self.follow(target, depth + 1)
            if isinstance(target, list):
                if len(target) == 4 and target[0] == "$" and key in _ELEMENT_KEYS:
                    target = target[_ELEMENT_KEYS[key]]
                elif key.isdigit() and int(key) < len(target):
                    target = target[int(key)]
                else:
                    return None
            elif isinstance(target, dict):
                target = target.get(key)
            else:
                return None
        return self.follow(target, depth + 1)

    def resolve(self, value: Any, depth: int = 0) -> Any:
        """``value`` with every reference inside it replaced by what it points to."""
        if depth > _MAX_DEPTH:
            return value
        if isinstance(value, str):
            followed = self.follow(value)
            return value if followed is value else self.resolve(followed, depth + 1)
        if isinstance(value, list):
            return [self.resolve(item, depth + 1) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(item, depth + 1) for key, item in value.items()}
        return value

    def find(self, key: str) -> Iterator[dict[str, Any]]:
        """Every dict (in any row) that has ``key``, unresolved, in payload order."""
        for row in self.rows.values():
            yield from _dicts_with(row, key)

    def first(self, key: str) -> dict[str, Any] | None:
        """The first dict that has ``key``, with its references resolved."""
        for found in self.find(key):
            return self.resolve(found)
        return None

    def keyed(self, prefix: str) -> Iterator[tuple[str, Any]]:
        """``(key, value)`` for every dict entry whose key starts with ``prefix``.

        Glassdoor's data cache keys its entries by the request they came from
        (``#url:"/bff/..."``,args:#page:2,...``), so the key itself carries the query.
        """
        stack = list(self.rows.values())
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if key.startswith(prefix):
                        yield key, value
                    else:
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)

    def json_value(self, value: Any) -> Any:
        """A resolved value; a text row that holds JSON (``T`` rows) is decoded."""
        value = self.resolve(value)
        if isinstance(value, str) and value[:1] in "[{":
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value


def _dicts_with(value: Any, key: str) -> Iterator[dict[str, Any]]:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if key in item:
                yield item
            stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))
