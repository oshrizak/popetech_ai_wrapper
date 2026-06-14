"""Projection, filtering, and sorting helpers.

These let the query CLI trim large API responses down to just the fields that
answer a question, and do the filter/sort/top-N work in-tool instead of forcing
the caller to post-process huge payloads.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

MISSING = object()


def pluck(obj: Any, path: str, default: Any = None) -> Any:
    """Resolve a dotted path into nested dicts/lists.

    ``pluck(d, "data.results.errors.total")`` walks dict keys; integer segments
    index into lists (``"items.0.name"``). Returns ``default`` if any segment is
    missing.
    """
    cur = obj
    for part in path.split("."):
        if isinstance(cur, Mapping):
            if part in cur:
                cur = cur[part]
            else:
                return default
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return cur


def project(item: Any, fields: Optional[Sequence[str]]) -> Any:
    """Reduce ``item`` to only the requested dotted ``fields``.

    Keys in the result are the field paths as given, so they stay unambiguous.
    If ``fields`` is falsy, the item is returned unchanged.
    """
    if not fields:
        return item
    out = {}
    for f in fields:
        value = pluck(item, f, MISSING)
        if value is not MISSING:
            out[f] = value
    return out


# -- filtering -------------------------------------------------------------

# Two-char operators must be tried before single-char ones.
_OPERATORS = ["!=", ">=", "<=", "~", "=", ">", "<"]
_COND_RE = re.compile(
    r"^(?P<path>.+?)(?P<op>!=|>=|<=|~|=|>|<)(?P<value>.*)$"
)


def parse_condition(expr: str) -> Tuple[str, str, str]:
    """Parse ``path<op>value`` (e.g. ``scan_count>0``) into its parts."""
    m = _COND_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Invalid filter expression: {expr!r}")
    return m.group("path").strip(), m.group("op"), m.group("value").strip()


def _as_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def match_condition(item: Any, path: str, op: str, value: str) -> bool:
    actual = pluck(item, path, MISSING)
    if actual is MISSING:
        return False

    a_num, v_num = _as_number(actual), _as_number(value)
    both_numeric = a_num is not None and v_num is not None

    if op == "=":
        if both_numeric:
            return a_num == v_num
        return str(actual).lower() == value.lower()
    if op == "!=":
        if both_numeric:
            return a_num != v_num
        return str(actual).lower() != value.lower()
    if op == "~":
        return value.lower() in str(actual).lower()
    if both_numeric:
        if op == ">":
            return a_num > v_num
        if op == "<":
            return a_num < v_num
        if op == ">=":
            return a_num >= v_num
        if op == "<=":
            return a_num <= v_num
    return False


def apply_filters(items: Iterable[Any], conditions: Sequence[str]) -> List[Any]:
    parsed = [parse_condition(c) for c in conditions]
    result = []
    for item in items:
        if all(match_condition(item, p, o, v) for p, o, v in parsed):
            result.append(item)
    return result


# -- sorting ---------------------------------------------------------------


def sort_items(items: List[Any], path: str, descending: bool = False) -> List[Any]:
    """Sort by a dotted path. Numeric values sort numerically; missing/None
    values are always placed last, regardless of direction."""

    def key(value: Any) -> Tuple[int, Any]:
        # (type_rank, value) avoids comparing float against str.
        num = _as_number(value)
        return (0, num) if num is not None else (1, str(value).lower())

    present, missing = [], []
    for item in items:
        value = pluck(item, path, MISSING)
        (missing if value is MISSING or value is None else present).append(item)

    present.sort(key=lambda it: key(pluck(it, path)), reverse=descending)
    return present + missing
