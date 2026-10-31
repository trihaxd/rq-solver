"""The calendar every interface shares.

The lecture notes' year: 52 weeks of 7 days and 12 months. Keeping it here
rather than in ``webapp`` lets the derivation module and the terminal
walkthrough convert without importing the web layer.
"""

from __future__ import annotations

from rq_solver import SolverError

__all__ = ["UNITS", "convert", "unit_label", "unit_plural"]

#: Fractions of a year. "Two weeks of a year" is then exactly the 2/52 the deck
#: uses, and 14 days comes to the same number instead of drifting to 14/365.
UNITS = {
    "year":  {"label": "year",  "plural": "years",  "per_year": 1.0},
    "month": {"label": "month", "plural": "months", "per_year": 1.0 / 12.0},
    "week":  {"label": "week",  "plural": "weeks",  "per_year": 1.0 / 52.0},
    "day":   {"label": "day",   "plural": "days",   "per_year": 1.0 / 364.0},
}


def convert(value: float, source: str, target: str) -> float:
    """Re-express a length of time from one unit in another."""
    for name in (source, target):
        if name not in UNITS:
            raise SolverError(f"Unknown time unit: {name!r}")
    return value * UNITS[source]["per_year"] / UNITS[target]["per_year"]


def unit_label(name: str) -> str:
    if name not in UNITS:
        raise SolverError(f"Unknown time unit: {name!r}")
    return UNITS[name]["label"]


def unit_plural(name: str) -> str:
    if name not in UNITS:
        raise SolverError(f"Unknown time unit: {name!r}")
    return UNITS[name]["plural"]
