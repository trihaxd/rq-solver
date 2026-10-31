"""What has to be worked out before the iteration can start.

Homework 2 states its data the way a company holds it — a carrying *charge*
against the unit cost, and demand per month or per week — not the way the cost
function wants it: a holding cost ``h`` per unit per unit time, and the
distribution of demand *over the lead time*. Problem 1 asks for that conversion
outright ("compute expected annual demand during lead time, variance of annual
demand during lead time"), so it is work to be shown, not plumbing to hide.

Each conversion returns the same ``{label, tex, plain}`` shape ``steps`` uses,
so the terminal walkthrough and the page print them through the same code path
as the iteration itself.

Two conversions, both independent of each other:

``h = v · r``
    A carrying charge ``r`` is dollars held per dollar of stock per unit time,
    so the holding cost is the charge times the unit cost. The charge carries
    its own time unit (0.3 $/$/year, 0.1 $/$/week) and is re-expressed in the
    base unit first.

``θ = μ·k,  σ = s·√k``
    Demand recorded per period, over ``k`` periods of lead time. The periods
    are independent, so means add and *variances* add — the standard deviation
    grows with the square root, which is the step a manual solution most often
    gets wrong. Per-period demand may also be Uniform(lo, hi) — giving
    Uniform(lo·k, hi·k) — or Exponential(mean m) — giving Exponential(mean m·k).
    Those two are the lecture's simplification (Homework 2, Problem 3): the
    bounds or the mean are scaled, though the exact sum would not keep the shape.

``p = b · v``
    A backorder cost stated as a fraction of the unit cost (Problem 3,
    Scenario 2: 30 %). The v is the model's: the one the holding derivation
    used, if it ran, otherwise the unit cost the caller passes in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rq_solver import Exponential, Normal, SolverError, Uniform, build_distribution
from timeunits import UNITS, convert, unit_label, unit_plural

__all__ = ["Derivation", "derive", "rate_per", "DERIVE_FIELDS",
           "PERIOD_DISTRIBUTIONS"]

#: The per-period demand laws ``derive`` can carry over the lead time.
PERIOD_DISTRIBUTIONS = ("Normal", "Uniform", "Exponential")


def g(x: float) -> str:
    """A number roughly as it was typed: 0.3, 28, 0.269231."""
    return f"{x:.6g}"


def n(x: float, dp: int = 3) -> str:
    return f"{x:.3f}"


def rate_per(value: float, source: str, target: str) -> float:
    """Re-express a rate *per source unit* as a rate *per target unit*.

    A length of time converts one way and a rate the other, so this is
    :func:`convert` with its arguments swapped rather than a second table.
    0.3 per year is 0.3/52 per week.
    """
    return convert(value, target, source)


# --------------------------------------------------------------------------- #
#  What the interfaces offer
# --------------------------------------------------------------------------- #

#: The fields each derivation mode needs, for the page to draw and the terminal
#: walkthrough to prompt for. ``direct`` modes need nothing and are the default,
#: so nothing about the existing form changes unless a mode is switched.
DERIVE_FIELDS = {
    "holding": {
        "label": "Holding cost",
        "modes": {
            "direct": {"label": "Enter h directly", "fields": []},
            "rate": {
                "label": "From a carrying charge  h = v·r",
                "fields": [
                    {"key": "v", "label": "Unit cost", "symbol": "v",
                     "default": 6.0, "help": "Dollars per unit."},
                    {"key": "carrying_rate", "label": "Carrying charge",
                     "symbol": "r", "default": 0.3, "unit": "rate",
                     "help": "Dollars held per dollar of stock per unit time."},
                ],
            },
        },
    },
    "demand": {
        "label": "Lead-time demand",
        "modes": {
            "direct": {"label": "Enter the lead-time distribution", "fields": []},
            "period": {
                "label": "From demand per period",
                # The Normal fields, kept here for every caller that predates
                # the other two laws; `fields_by_dist` has all three. The
                # request names its law as `dist` (Normal when absent).
                "fields": [
                    # Short labels: the rail is narrow, and the unit picker
                    # beside the mean already says which period it is.
                    {"key": "mean", "label": "Mean demand",
                     "symbol": "μ", "default": 28.0, "unit": "period",
                     "help": "Average demand in one period."},
                    {"key": "sigma", "label": "Std. deviation",
                     "symbol": "s", "default": 8.0,
                     "help": "Standard deviation of demand in one period."},
                ],
                "dists": list(PERIOD_DISTRIBUTIONS),
                "fields_by_dist": {
                    "Normal": [
                        {"key": "mean", "label": "Mean demand",
                         "symbol": "μ", "default": 28.0, "unit": "period",
                         "help": "Average demand in one period."},
                        {"key": "sigma", "label": "Std. deviation",
                         "symbol": "s", "default": 8.0,
                         "help": "Standard deviation of demand in one period."},
                    ],
                    "Uniform": [
                        {"key": "lo", "label": "Lowest demand",
                         "symbol": "lo", "default": 0.25, "unit": "period",
                         "help": "Least demand in one period. Over k periods "
                                 "the bounds are scaled by k (the lecture's "
                                 "simplification)."},
                        {"key": "hi", "label": "Highest demand",
                         "symbol": "hi", "default": 1.0,
                         "help": "Most demand in one period."},
                    ],
                    "Exponential": [
                        {"key": "mean", "label": "Mean demand",
                         "symbol": "m", "default": 0.1, "unit": "period",
                         "help": "Average demand in one period. Over k periods "
                                 "the mean is scaled by k (the lecture's "
                                 "simplification)."},
                    ],
                },
            },
        },
    },
    "penalty": {
        "label": "Penalty cost",
        "modes": {
            "direct": {"label": "Enter p directly", "fields": []},
            "fraction": {
                "label": "As a fraction of unit cost  p = b·v",
                "fields": [
                    {"key": "b", "label": "Fraction of unit cost", "symbol": "b",
                     "default": 0.3,
                     "help": "Backorder cost per unit short as a share of v: "
                             "0.30 for 30 %."},
                ],
            },
        },
    },
}


@dataclass
class Derivation:
    """Whatever was worked out, and the working behind it.

    A field is ``None`` when its mode was ``direct``: the caller keeps the
    number the user typed.
    """

    h: float | None = None
    #: The unit cost the holding derivation used. The cost function also
    #: charges D·v, and two boxes for one v is two numbers that can disagree —
    #: so when h comes from v·r, that same v is the one the model is given.
    v: float | None = None
    D: float | None = None
    theta: float | None = None
    #: The standard deviation of lead-time demand, whatever its law.
    sigma: float | None = None
    #: The lead-time law and its registry parameters, when demand per period
    #: was given: "Normal" {mu, sigma}, "Uniform" {a, b}, "Exponential" {mean}.
    dist_name: str | None = None
    dist_params: dict | None = None
    #: The penalty cost, when it came from p = b·v.
    p: float | None = None
    steps: list = field(default_factory=list)

    @property
    def used(self) -> bool:
        return bool(self.steps)

    def distribution(self):
        """The derived lead-time demand as a Distribution, or None."""
        if self.dist_name is None:
            return None
        return build_distribution(self.dist_name, self.dist_params)


# --------------------------------------------------------------------------- #
#  h = v · r
# --------------------------------------------------------------------------- #

def _holding(spec: dict, base_unit: str) -> tuple:
    v = _number(spec.get("v"), "unit cost v")
    rate = _number(spec.get("carrying_rate"), "carrying charge r")
    rate_unit = spec.get("rate_unit") or base_unit
    if rate_unit not in UNITS:
        raise SolverError(f"Unknown carrying-charge time unit: {rate_unit!r}")
    if v <= 0.0:
        raise SolverError("The unit cost v must be greater than zero to derive h from it.")
    if rate <= 0.0:
        raise SolverError("The carrying charge r must be greater than zero.")

    base = unit_label(base_unit)
    steps = []
    in_base = rate
    if rate_unit != base_unit:
        in_base = rate_per(rate, rate_unit, base_unit)
        steps.append({
            "label": f"Put the carrying charge on the {base}",
            "tex": (rf"r={g(rate)}\ \tfrac{{\$}}{{\$\cdot\text{{{unit_label(rate_unit)}}}}}"
                    rf"\times\dfrac{{1\ \text{{{base}}}}}"
                    rf"{{{g(convert(1.0, base_unit, rate_unit))}\ \text{{{unit_plural(rate_unit)}}}}}"
                    rf"={n(in_base, 6)}\ \tfrac{{\$}}{{\$\cdot\text{{{base}}}}}"),
            "plain": (f"r = {g(rate)} $/$/{unit_label(rate_unit)}"
                      f" / {g(convert(1.0, base_unit, rate_unit))}"
                      f" = {n(in_base, 6)} $/$/{base}"),
        })
    h = v * in_base
    steps.append({
        "label": "Holding cost from the carrying charge",
        "tex": (r"h=v\,r=" rf"({g(v)})({g(in_base)})={n(h, 6)}"
                rf"\ \tfrac{{\$}}{{\text{{unit}}\cdot\text{{{base}}}}}"),
        "plain": f"h = v·r = ({g(v)})({g(in_base)}) = {n(h, 6)} $/unit/{base}",
    })
    return h, v, steps


# --------------------------------------------------------------------------- #
#  D, theta and sigma from demand per period
# --------------------------------------------------------------------------- #

def _demand(spec: dict, base_unit: str, lead_in_base: float) -> tuple:
    """Normal per-period demand (the default), or Uniform / Exponential.

    Returns ``(D, theta, sigma, steps, dist_name, dist_params)``; the params
    are in the registry's keys for that distribution, ready for
    ``build_distribution``.
    """
    law = spec.get("dist") or "Normal"
    if law not in PERIOD_DISTRIBUTIONS:
        raise SolverError(
            f"Demand per period can be Normal, Uniform or Exponential, not {law!r}. "
            "Enter the lead-time distribution directly instead.")
    if law != "Normal":
        return _demand_scaled(spec, law, base_unit, lead_in_base)

    mean = _number(spec.get("mean"), "mean demand per period")
    sigma = _number(spec.get("sigma"), "standard deviation per period")
    period, k, per_base, steps = _period_span(spec, base_unit, lead_in_base)
    if mean <= 0.0:
        raise SolverError("The mean demand per period must be greater than zero.")
    if sigma < 0.0:
        raise SolverError("The standard deviation per period cannot be negative.")

    D = mean * per_base
    # The aggregation itself is `Normal.from_period`, which already guards the
    # variance and the span. Doing the arithmetic again here would be a second
    # place for it to be wrong.
    aggregated = Normal.from_period(mean, sigma * sigma, k)
    theta, sd = aggregated.mu, aggregated.sigma
    variance = sd * sd

    steps = _rate_steps(mean, D, period, base_unit, per_base) + steps
    steps += [
        {"label": "Expected demand over the lead time",
         "tex": (rf"\theta=\mu\,k=({g(mean)})({n(k, 6)})={n(theta, 6)}"),
         "plain": f"theta = mu·k = ({g(mean)})({n(k, 6)}) = {n(theta, 6)}"},
        {"label": "Variance over the lead time — variances add, not deviations",
         "tex": (rf"\sigma_L^2=s^2k=({g(sigma)})^2({n(k, 6)})={n(variance, 6)}"),
         "plain": f"var = s^2·k = ({g(sigma)})^2({n(k, 6)}) = {n(variance, 6)}"},
        {"label": "Standard deviation over the lead time",
         "tex": (rf"\sigma_L=s\sqrt{{k}}=({g(sigma)})\sqrt{{{n(k, 6)}}}={n(sd, 6)}"),
         "plain": f"sigma = s·sqrt(k) = ({g(sigma)})sqrt({n(k, 6)}) = {n(sd, 6)}"},
    ]
    return D, theta, sd, steps, "Normal", {"mu": theta, "sigma": sd}


def _period_span(spec: dict, base_unit: str, lead_in_base: float) -> tuple:
    """The period unit, the lead time counted in it, and periods per base unit.

    Returns ``(period, k, per_base, steps)``: the step that counts the lead
    time in periods, which is empty when the period is the base unit.
    """
    period = spec.get("period_unit") or base_unit
    if period not in UNITS:
        raise SolverError(f"Unknown demand period unit: {period!r}")
    if lead_in_base < 0.0:
        raise SolverError("The lead time cannot be negative.")
    #: How many of those periods make one base unit, and how many the lead time
    #: spans. One year is 12 months; a 14-week lead time is 3.2308 months.
    per_base = convert(1.0, base_unit, period)
    k = convert(lead_in_base, base_unit, period)
    steps = []
    # When demand is already recorded on the base unit there is nothing to
    # rescale, and printing "× 1 weeks/week" only buries the steps that matter.
    if period != base_unit:
        pers = unit_plural(period)
        steps.append(
            {"label": f"The lead time, counted in {pers}",
             "tex": rf"k={g(lead_in_base)}\ \text{{{unit_plural(base_unit)}}}\times"
                    rf"{g(per_base)}={n(k, 6)}\ \text{{{pers}}}",
             "plain": (f"k = {g(lead_in_base)} {unit_plural(base_unit)}"
                       f" × {g(per_base)} = {n(k, 6)} {pers}")})
    return period, k, per_base, steps


def _rate_steps(mean: float, D: float, period: str, base_unit: str,
                per_base: float, mean_tex: str = "", mean_plain: str = "") -> list:
    """The step that puts the demand rate on the base unit, if it needs one."""
    if period == base_unit:
        return []
    base = unit_label(base_unit)
    per = unit_label(period)
    pers = unit_plural(period)
    return [
        {"label": f"Demand rate on the {base}",
         "tex": (rf"D={mean_tex}{g(mean)}\ \tfrac{{\text{{units}}}}{{\text{{{per}}}}}"
                 rf"\times{g(per_base)}\ \tfrac{{\text{{{pers}}}}}{{\text{{{base}}}}}"
                 rf"={n(D, 6)}\ \tfrac{{\text{{units}}}}{{\text{{{base}}}}}"),
         "plain": (f"D = {mean_plain}{g(mean)} units/{per} × {g(per_base)} {pers}/{base}"
                   f" = {n(D, 6)} units/{base}")}]


def _demand_scaled(spec: dict, law: str, base_unit: str, lead_in_base: float) -> tuple:
    """Uniform or Exponential per-period demand, stretched over k periods.

    Uniform(lo, hi) per period becomes Uniform(lo·k, hi·k) over the lead time,
    and Exponential(mean m) becomes Exponential(mean m·k). Both are the
    lecture's simplification, not an exact convolution: a sum of independent
    uniforms is not uniform (two of them already make a triangle), and a sum of
    exponentials is Erlang. The steps say so where they make the move.
    """
    period, k, per_base, span = _period_span(spec, base_unit, lead_in_base)
    if k <= 0.0:
        raise SolverError("Lead time must be positive.")
    base = unit_label(base_unit)
    per = unit_label(period)

    if law == "Uniform":
        lo = _number(spec.get("lo"), "lowest demand per period")
        hi = _number(spec.get("hi"), "highest demand per period")
        if lo < 0.0:
            raise SolverError("The lowest demand per period cannot be negative.")
        if not hi > lo:
            raise SolverError("The highest demand per period must be above the lowest.")
        mean = (lo + hi) / 2.0
        D = mean * per_base
        a, b = lo * k, hi * k
        dist = Uniform(a, b)
        steps = [
            {"label": f"Mean demand per {per}, the middle of the range",
             "tex": (rf"\mu=\dfrac{{lo+hi}}{{2}}=\dfrac{{{g(lo)}+{g(hi)}}}{{2}}"
                     rf"={n(mean, 6)}"),
             "plain": f"mu = (lo + hi)/2 = ({g(lo)} + {g(hi)})/2 = {n(mean, 6)}"},
        ]
        steps += _rate_steps(mean, D, period, base_unit, per_base)
        steps += span
        steps += [
            {"label": ("Lead-time demand: scale both bounds by k — the lecture's "
                       "simplification; a sum of uniforms is not exactly uniform"),
             "tex": (rf"a=lo\,k=({g(lo)})({n(k, 6)})={n(a, 6)},\quad "
                     rf"b=hi\,k=({g(hi)})({n(k, 6)})={n(b, 6)}"),
             "plain": (f"a = lo·k = ({g(lo)})({n(k, 6)}) = {n(a, 6)},  "
                       f"b = hi·k = ({g(hi)})({n(k, 6)}) = {n(b, 6)}")},
            {"label": "Expected demand over the lead time",
             "tex": rf"\theta=\dfrac{{a+b}}{{2}}={n(dist.mean, 6)}",
             "plain": f"theta = (a + b)/2 = {n(dist.mean, 6)}"},
        ]
        return D, dist.mean, dist.stdev, steps, "Uniform", {"a": a, "b": b}

    mean = _number(spec.get("mean"), "mean demand per period")
    if mean <= 0.0:
        raise SolverError("The mean demand per period must be greater than zero.")
    D = mean * per_base
    lead_mean = mean * k
    dist = Exponential.from_mean(lead_mean)
    steps = _rate_steps(mean, D, period, base_unit, per_base)
    steps += span
    steps += [
        {"label": ("Lead-time demand: scale the mean by k — the lecture's "
                   "simplification; a sum of exponentials is Erlang, not exponential"),
         "tex": rf"\theta=m\,k=({g(mean)})({n(k, 6)})={n(lead_mean, 6)}",
         "plain": f"theta = m·k = ({g(mean)})({n(k, 6)}) = {n(lead_mean, 6)}"},
        {"label": "The exponential's rate over the lead time",
         "tex": rf"\lambda=\dfrac{{1}}{{\theta}}=\dfrac{{1}}{{{n(lead_mean, 6)}}}"
                rf"={n(dist.lam, 6)}",
         "plain": f"lambda = 1/theta = 1/{n(lead_mean, 6)} = {n(dist.lam, 6)}"},
    ]
    return (D, lead_mean, dist.stdev, steps, "Exponential", {"mean": lead_mean})


# --------------------------------------------------------------------------- #
#  p = b · v
# --------------------------------------------------------------------------- #

def _penalty(spec: dict, v: float | None) -> tuple:
    b = _number(spec.get("b"), "fraction of unit cost b")
    if b <= 0.0:
        raise SolverError("The fraction b in p = b·v must be greater than zero.")
    if v is None or not math.isfinite(v) or v <= 0.0:
        raise SolverError(
            "Deriving the penalty cost as p = b·v needs the unit cost v; enter v "
            "(or derive h from a carrying charge, which supplies it).")
    p = b * v
    return p, [{
        "label": "Penalty cost as a fraction of the unit cost",
        "tex": rf"p=b\,v=({g(b)})({g(v)})={n(p, 6)}\ \tfrac{{\$}}{{\text{{unit short}}}}",
        "plain": f"p = b·v = ({g(b)})({g(v)}) = {n(p, 6)} $/unit short",
    }]


# --------------------------------------------------------------------------- #

def _number(raw, label: str) -> float:
    if raw is None:
        raise SolverError(f"The {label} is missing.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise SolverError(f"The {label} is not a number: {raw!r}") from None
    if not math.isfinite(value):
        raise SolverError(f"The {label} must be an ordinary number; it is {value}.")
    return value


def derive(spec: dict | None, base_unit: str, lead_in_base: float,
           v: float | None = None) -> Derivation:
    """Work out whatever the chosen modes ask for, and show the working.

    ``spec`` is ``{"holding": {...}, "demand": {...}, "penalty": {...}}``; a
    block whose ``mode`` is missing or ``"direct"`` is skipped, so an absent
    ``spec`` means nothing is derived and the caller's own numbers stand.
    ``v`` is the caller's unit cost, used by ``p = b·v`` unless the holding
    derivation supplies its own.
    """
    out = Derivation()
    if not spec:
        return out
    if not isinstance(spec, dict):
        raise SolverError("The derivation block must be a JSON object.")

    holding = spec.get("holding") or {}
    if holding.get("mode") == "rate":
        out.h, out.v, steps = _holding(holding, base_unit)
        out.steps += steps

    demand = spec.get("demand") or {}
    if demand.get("mode") == "period":
        (out.D, out.theta, out.sigma, steps,
         out.dist_name, out.dist_params) = _demand(demand, base_unit, lead_in_base)
        out.steps += steps

    penalty = spec.get("penalty") or {}
    if penalty.get("mode") == "fraction":
        out.p, steps = _penalty(penalty, out.v if out.v is not None else v)
        out.steps += steps

    return out
