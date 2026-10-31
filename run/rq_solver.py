"""Iterative solution of the continuous-review (r, Q) model.

Chapter 2 — Individual Item with Probabilistic Demand
(Silver, Pyke & Thomas, *Inventory and Production Management in Supply Chains*, 4th ed.)

Cost model (penalty cost p per unit short)::

    Y(Q, r) = h·(Q/2 + r − D·l) + A·D/Q + p·D·n(r)/Q + D·v

Setting the two partial derivatives to zero gives the pair that the procedure
iterates between::

    (1)  Q = sqrt( 2·D·[A + p·n(r)] / h )
    (2)  1 − G(r) = Q·h / (p·D)

with ``n(r) = E[max(X − r, 0)]`` the expected shortage per replenishment cycle
and ``G`` the cdf of lead-time demand X.

Procedure (slides 23–24): start from ``Q0 = EOQ = sqrt(2AD/h)``, get r from (2),
then n(r), then Q from (1), and repeat until r stops changing.

That is the default *stockout basis*, ``B2`` — a cost p per unit short. Three
more bases are offered (``Inputs.stockout``), each its own pair of conditions:

``B1``     a cost B1 per stockout *occasion* (slide 15, Silver-Pyke-Thomas):
           Y = A·D/Q + h(Q/2 + r − θ) + B1·(D/Q)·(1 − G(r)), iterated between
           (1') Q = sqrt(2D[A + B1·(1 − G(r))]/h) and (2') g(r) = Q·h/(B1·D).
``alpha``  a cycle service level (Type I): Q = EOQ and G(r) = α.
``beta``   a fill rate (Type II): Q = EOQ and n(r) = (1 − β)·Q.

Policy 2 — periodic review (R, S), slides 46–52 — reviews every T and orders up
to S; it protects against demand over T + L rather than L alone, and is solved
by :func:`solve_periodic`. :func:`compare_policies` puts the two side by side.

The module is pure standard library: no numpy, no scipy.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Sequence

__all__ = [
    "Distribution", "Uniform", "Exponential", "Normal", "Poisson",
    "Inputs", "Iteration", "Result", "solve_rq", "unit_normal_loss",
    "build_distribution", "DISTRIBUTIONS", "STOCKOUT_MODES",
    "PeriodicResult", "solve_periodic", "Comparison", "compare_policies",
    "example_review_period",
]

_STD_NORMAL = NormalDist(0.0, 1.0)


class SolverError(ValueError):
    """Raised when the inputs cannot produce a meaningful (r, Q)."""


def unit_normal_loss(k: float) -> float:
    """G_u(k) = phi(k) − k·(1 − Phi(k)), the unit normal loss function."""
    pdf = math.exp(-0.5 * k * k) / math.sqrt(2.0 * math.pi)
    return pdf - k * (1.0 - _STD_NORMAL.cdf(k))


# --------------------------------------------------------------------------- #
#  Lead-time demand distributions
# --------------------------------------------------------------------------- #

class Distribution:
    """Lead-time demand distribution.

    A subclass supplies the cdf, the inverse cdf and the loss function
    ``n(r) = integral_r^inf (x − r)·g(x) dx`` (a sum, for a discrete law).
    """

    name: str = "distribution"
    discrete: bool = False

    @property
    def mean(self) -> float:
        raise NotImplementedError

    @property
    def stdev(self) -> float:
        raise NotImplementedError

    @property
    def support_low(self) -> float:
        raise NotImplementedError

    def cdf(self, x: float) -> float:
        raise NotImplementedError

    def inv_cdf(self, u: float) -> float:
        raise NotImplementedError

    def loss(self, r: float) -> float:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def params(self) -> dict:
        """The registry fields (``DISTRIBUTIONS[name]["fields"]``) and their values."""
        raise NotImplementedError

    def scaled(self, f: float) -> "Distribution":
        """The same law stretched over ``f`` times the time span.

        Policy 2 protects against demand over the review period plus the lead
        time, T + L, and gets that distribution by scaling lead-time demand by
        ``f = (T + L)/L``. Each subclass says what scaling means for it.
        """
        raise NotImplementedError

    @staticmethod
    def _check_factor(f: float) -> float:
        if not math.isfinite(f) or f <= 0.0:
            raise SolverError(
                f"A distribution can only be scaled by a positive, finite factor; got {f}.")
        return f

    # Shared guard for the inverse cdf.
    @staticmethod
    def _check_u(u: float) -> float:
        if not 0.0 < u < 1.0:
            raise SolverError(
                f"Equation (2) asks for the {u:.6g} quantile of lead-time demand, "
                "which is outside (0, 1)."
            )
        return u


@dataclass(frozen=True)
class Uniform(Distribution):
    """Uniform lead-time demand on [a, b]."""

    a: float
    b: float
    name: str = field(default="Uniform", init=False)
    discrete: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.a) and math.isfinite(self.b)):
            raise SolverError("The Uniform bounds must be finite numbers.")
        if not self.b > self.a:
            raise SolverError("Uniform distribution needs b > a.")

    @property
    def mean(self) -> float:
        return (self.a + self.b) / 2.0

    @property
    def stdev(self) -> float:
        return (self.b - self.a) / math.sqrt(12.0)

    @property
    def support_low(self) -> float:
        return self.a

    def cdf(self, x: float) -> float:
        if x <= self.a:
            return 0.0
        if x >= self.b:
            return 1.0
        return (x - self.a) / (self.b - self.a)

    def inv_cdf(self, u: float) -> float:
        self._check_u(u)
        return self.a + u * (self.b - self.a)

    def loss(self, r: float) -> float:
        if r <= self.a:
            return self.mean - r
        if r >= self.b:
            return 0.0
        return (self.b - r) ** 2 / (2.0 * (self.b - self.a))

    def describe(self) -> str:
        return f"Uniform({self.a:g}, {self.b:g})"

    def params(self) -> dict:
        return {"a": self.a, "b": self.b}

    def scaled(self, f: float) -> "Uniform":
        # The lecture's convention (slide 25 builds lead-time demand this way):
        # stretch both bounds. The exact sum of independent uniforms is not
        # uniform at all — it is a simplification the user chose knowingly.
        self._check_factor(f)
        return Uniform(self.a * f, self.b * f)


@dataclass(frozen=True)
class Exponential(Distribution):
    """Exponential lead-time demand with rate ``lam`` (mean 1/lam)."""

    lam: float
    name: str = field(default="Exponential", init=False)
    discrete: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.lam) or self.lam <= 0.0:
            raise SolverError("The Exponential rate must be a positive, finite number.")

    @classmethod
    def from_mean(cls, mean: float) -> "Exponential":
        if not math.isfinite(mean) or mean <= 0.0:
            raise SolverError("The Exponential mean must be a positive, finite number.")
        return cls(1.0 / mean)

    @property
    def mean(self) -> float:
        return 1.0 / self.lam

    @property
    def stdev(self) -> float:
        return 1.0 / self.lam

    @property
    def support_low(self) -> float:
        return 0.0

    def cdf(self, x: float) -> float:
        if x <= 0.0:
            return 0.0
        return 1.0 - math.exp(-self.lam * x)

    def inv_cdf(self, u: float) -> float:
        self._check_u(u)
        return -math.log1p(-u) / self.lam

    def loss(self, r: float) -> float:
        if r <= 0.0:
            return self.mean - r
        return math.exp(-self.lam * r) / self.lam

    def describe(self) -> str:
        return f"Exponential(lambda={self.lam:g}, mean={self.mean:g})"

    def params(self) -> dict:
        return {"mean": self.mean}

    def scaled(self, f: float) -> "Exponential":
        # Scale the mean, keep the shape. As with Uniform this is the lecture's
        # simplification: a sum of exponentials is Erlang, not exponential.
        self._check_factor(f)
        return Exponential.from_mean(self.mean * f)


@dataclass(frozen=True)
class Normal(Distribution):
    """Normal lead-time demand N(mu, sigma²)."""

    mu: float
    sigma: float
    name: str = field(default="Normal", init=False)
    discrete: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.mu):
            raise SolverError("The Normal mean must be a finite number.")
        if not math.isfinite(self.sigma) or self.sigma <= 0.0:
            raise SolverError(
                "The Normal standard deviation must be a positive, finite number.")

    @classmethod
    def from_period(cls, d: float, var_per_period: float, lead_time: float) -> "Normal":
        """Aggregate i.i.d. per-period demand N(d, var) over ``lead_time`` periods."""
        if var_per_period < 0.0:
            raise SolverError("Per-period variance cannot be negative.")
        if lead_time <= 0.0:
            raise SolverError("Lead time must be positive.")
        return cls(d * lead_time, math.sqrt(var_per_period * lead_time))

    @property
    def mean(self) -> float:
        return self.mu

    @property
    def stdev(self) -> float:
        return self.sigma

    @property
    def support_low(self) -> float:
        return -math.inf

    def cdf(self, x: float) -> float:
        return NormalDist(self.mu, self.sigma).cdf(x)

    def inv_cdf(self, u: float) -> float:
        self._check_u(u)
        return self.mu + self.sigma * _STD_NORMAL.inv_cdf(u)

    def loss(self, r: float) -> float:
        return self.sigma * unit_normal_loss((r - self.mu) / self.sigma)

    def describe(self) -> str:
        return f"Normal(mu={self.mu:g}, sigma={self.sigma:g})"

    def params(self) -> dict:
        return {"mu": self.mu, "sigma": self.sigma}

    def scaled(self, f: float) -> "Normal":
        # Independent periods: the mean grows with f, the variance with f too,
        # so the deviation with sqrt(f) — exact, unlike Uniform and Exponential.
        self._check_factor(f)
        return Normal(self.mu * f, self.sigma * math.sqrt(f))

    def pdf(self, x: float) -> float:
        z = (x - self.mu) / self.sigma
        return math.exp(-0.5 * z * z) / (self.sigma * math.sqrt(2.0 * math.pi))


@dataclass(frozen=True)
class Poisson(Distribution):
    """Poisson lead-time demand with mean ``lam`` (an extension of the deck).

    Discrete, so the reorder point is the smallest integer r with G(r) >= target.

    The cdf, the survival function and the loss function come from one table
    built on first use over the window ``lam +/- 12*sqrt(lam)``, which holds all
    but about 1e-32 of the mass. Every probability in it is evaluated in log
    space, so nothing underflows for a large mean: a direct ``exp(-lam)``
    recurrence silently collapses to zero once ``lam`` passes about 745.
    """

    lam: float
    name: str = field(default="Poisson", init=False)
    discrete: bool = field(default=True, init=False)

    _MAX_MEAN = 1e9
    _WIDTH = 12.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.lam) or self.lam <= 0.0:
            raise SolverError("The Poisson mean must be a positive, finite number.")
        if self.lam > self._MAX_MEAN:
            raise SolverError(
                f"A Poisson mean above {self._MAX_MEAN:g} is not supported. At that "
                "size use Normal with mu = mean and sigma = sqrt(mean), which is the "
                "standard approximation."
            )
        object.__setattr__(self, "_table", None)

    # -- table ---------------------------------------------------------- #
    def _tables(self):
        """(lo, hi, cum, surv, loss) with index i standing for the value lo + i."""
        cached = object.__getattribute__(self, "_table")
        if cached is not None:
            return cached

        sd = math.sqrt(self.lam)
        lo = max(0, int(math.floor(self.lam - self._WIDTH * sd - 30.0)))
        hi = int(math.ceil(self.lam + self._WIDTH * sd + 30.0))
        pmf = [self.pmf(k) for k in range(lo, hi + 1)]
        size = len(pmf)

        cum = [0.0] * size
        running = 0.0
        for i, prob in enumerate(pmf):
            running += prob
            cum[i] = running if running < 1.0 else 1.0

        # surv[i] = P(X >= lo + i),  loss[i] = n(lo + i); both built from the top
        # downwards so every term added is positive and nothing cancels.
        surv = [0.0] * (size + 1)
        loss = [0.0] * (size + 1)
        for i in range(size - 1, -1, -1):
            surv[i] = surv[i + 1] + pmf[i]
            loss[i] = loss[i + 1] + surv[i + 1]

        table = (lo, hi, cum, surv, loss)
        object.__setattr__(self, "_table", table)
        return table

    # -- interface ------------------------------------------------------ #
    @property
    def mean(self) -> float:
        return self.lam

    @property
    def stdev(self) -> float:
        return math.sqrt(self.lam)

    @property
    def support_low(self) -> float:
        return 0.0

    def pmf(self, k: int) -> float:
        if k < 0:
            return 0.0
        return math.exp(-self.lam + k * math.log(self.lam) - math.lgamma(k + 1.0))

    def cdf(self, x: float) -> float:
        if x < 0.0:
            return 0.0
        lo, hi, cum, _surv, _loss = self._tables()
        n = int(math.floor(x))
        if n < lo:
            return 0.0
        if n >= hi:
            return 1.0
        return cum[n - lo]

    def inv_cdf(self, u: float) -> float:
        self._check_u(u)
        lo, hi, cum, _surv, _loss = self._tables()
        index = bisect.bisect_left(cum, u)
        if index >= len(cum):
            return float(hi)
        return float(lo + index)

    def loss(self, r: float) -> float:
        """n(r) = sum over x >= r of (x - r)*P(X = x), exact for any real r."""
        lo, hi, _cum, surv, loss = self._tables()
        if r <= lo:
            return self.lam - r
        if r >= hi:
            return 0.0
        ceiling = math.ceil(r)
        index = int(ceiling) - lo
        # Between ceiling-1 and ceiling there is no mass, so shifting r up to the
        # next integer costs (ceiling - r) for every unit of demand at or above it.
        return loss[index] + (ceiling - r) * surv[index]

    def describe(self) -> str:
        return f"Poisson(mean={self.lam:g})"

    def params(self) -> dict:
        return {"mean": self.lam}

    def scaled(self, f: float) -> "Poisson":
        # Exact: independent Poisson counts add to a Poisson count.
        self._check_factor(f)
        return Poisson(self.lam * f)


#: Registry used by both front ends, so they can never drift apart.
DISTRIBUTIONS = {
    "Uniform": {
        "fields": [("a", "Lower bound a", 0.0), ("b", "Upper bound b", 200.0)],
        "help": "Spread evenly between a and b.",
        "taught": True,
    },
    "Exponential": {
        "fields": [("mean", "Mean of lead-time demand", 100.0)],
        "help": "Lead-time demand with a memoryless, right-skewed shape.",
        "taught": True,
    },
    "Normal": {
        "fields": [("mu", "Mean mu", 80.0), ("sigma", "Std deviation sigma", 4.0)],
        "help": "Give mu and sigma of demand over the whole lead time. "
                "For per-period data use mu = l·d and sigma = sqrt(l)·sigma_d.",
        "taught": True,
    },
    "Poisson": {
        "fields": [("mean", "Mean of lead-time demand", 80.0)],
        "help": "Discrete counts. Not in the lecture deck; included as an extension.",
        "taught": False,
    },
}


def build_distribution(name: str, params: dict) -> Distribution:
    """Build a distribution from the registry name and a dict of field values."""
    if name == "Uniform":
        return Uniform(float(params["a"]), float(params["b"]))
    if name == "Exponential":
        return Exponential.from_mean(float(params["mean"]))
    if name == "Normal":
        return Normal(float(params["mu"]), float(params["sigma"]))
    if name == "Poisson":
        return Poisson(float(params["mean"]))
    raise SolverError(f"Unknown distribution {name!r}.")


# --------------------------------------------------------------------------- #
#  Stockout bases
# --------------------------------------------------------------------------- #

#: The four ways a problem can price (or bound) running out, for every front
#: end to offer from one list. ``B2`` is the default and needs no extra field:
#: its p is the penalty-cost box every interface already has. The others carry
#: one number each, sent as ``value``.
STOCKOUT_MODES = {
    "B2": {
        "label": "Backorder cost per unit short",
        "symbol": "p",
        "tex": "p",
        "help": "A cost p for every unit short. This is the model of slides "
                "18–24 and the default.",
        "fields": [],
    },
    "B1": {
        "label": "Shortage cost per stockout occasion",
        "symbol": "B₁",
        "tex": "B_1",
        "help": "A fixed cost B1 each time a replenishment cycle runs out, however "
                "many units are short (slide 15).",
        "fields": [{"key": "value", "label": "Cost per stockout occasion",
                    "symbol": "B₁", "default": 300.0,
                    "help": "Dollars charged each time a cycle runs out."}],
    },
    "alpha": {
        "label": "Service level, Type I",
        "symbol": "α",
        "tex": r"\alpha",
        "help": "Slide 13, Type I: S(r, Q) ≈ G(r), the probability of no "
                "stockout in a replenishment cycle. Setting S = α, Q is the EOQ "
                "and r = G⁻¹(α), the α quantile of lead-time demand.",
        "fields": [{"key": "value", "label": "Service level",
                    "symbol": "α", "default": 0.98, "min": 0.0, "max": 1.0,
                    "help": "A fraction strictly between 0 and 1: 0.98 for 98 %."}],
    },
    "beta": {
        "label": "Service level, Type II",
        "symbol": "β",
        "tex": r"\beta",
        "help": "Slide 13, Type II: S(r, Q) ≈ 1 − B(r)/Q, the fraction of "
                "demand met from stock, where B(r) = n(r) is the expected "
                "shortage per cycle. Setting S = β, Q is the EOQ and "
                "n(r) = (1 − β)·Q.",
        "fields": [{"key": "value", "label": "Service level",
                    "symbol": "β", "default": 0.98, "min": 0.0, "max": 1.0,
                    "help": "A fraction strictly between 0 and 1: 0.98 for 98 %."}],
    },
}


def _density_root(dist: Distribution, x: float) -> tuple:
    """The reorder level where the density of demand falls to ``x``.

    This is the optimality condition of every B1 problem — g(r) = Q·h/(B1·D) for
    Policy 1, g(S) = h·T/B1 for Policy 2 — taken on the right tail, where the
    density is falling and the root is a minimum rather than a maximum.

    Returns ``(level, kind)``. ``kind`` is ``"root"`` for an interior root,
    ``"floor"`` when there is none and the level is pinned at its lowest
    allowed value (no safety stock justified), ``"top"`` for the Uniform's
    upper corner, and ``"global"`` when a discrete law's cheapest level lies
    below the right-tail root.
    """
    if dist.name == "Normal":
        # phi(k)/sigma = x  →  k = sqrt(2·ln(1/(x·sigma·sqrt(2π)))). If the log's
        # argument is at most 1 the density never reaches x, and slide 15 step 2
        # applies: k goes to the lowest value management allows. We take k = 0
        # (r = mu) and say so; a firm with another floor substitutes its own.
        arg = 1.0 / (x * dist.sigma * math.sqrt(2.0 * math.pi))
        if not arg > 1.0:
            return dist.mu, "floor"
        return dist.mu + math.sqrt(2.0 * math.log(arg)) * dist.sigma, "root"
    if dist.name == "Exponential":
        # lambda·e^(−lambda·r) = x. The density is highest at 0 and only falls,
        # so x >= lambda leaves no root above zero.
        if x >= dist.lam:
            return 0.0, "floor"
        return math.log(dist.lam / x) / dist.lam, "root"
    if dist.name == "Uniform":
        # A flat density: the cost is linear in r on [a, b] with slope
        # h − B1·D/(Q·(b − a)) (per unit of the scale), so the minimum is a corner.
        if x < 1.0 / (dist.b - dist.a):
            return dist.b, "top"
        return dist.a, "floor"
    if dist.discrete:
        # Moving r up by one costs h and saves B1·D/Q · P(X = r + 1), so on the
        # right tail (r at or past the mode floor(lambda), where the pmf only
        # falls) stop at the first r with P(X = r + 1) <= x.
        lo, hi, _cum, _surv, _loss = dist._tables()
        r = max(int(math.floor(dist.lam)), 0)
        while r < hi and dist.pmf(r + 1) > x:
            r += 1
        # The cost is not convex in r over the whole line, so check the levels
        # below too: proportional to r + (1 − G(r))/x. Below the table every
        # level has 1 − G = 1, so 0 is the only one there worth trying.
        def cost(k):
            return k + (1.0 - dist.cdf(k)) / x
        best, best_cost = r, cost(r)
        for k in [0] + list(range(max(lo, 1), r)):
            c = cost(k)
            if c < best_cost - 1e-12 * max(1.0, abs(best_cost)):
                best, best_cost = k, c
        if best != r:
            return float(best), ("floor" if best == 0 else "global")
        return float(r), "root"
    raise SolverError(f"No density condition for {dist.name}.")


def _loss_root(dist: Distribution, target: float) -> tuple:
    """The lowest level whose expected shortage n(level) is at most ``target``.

    The fill-rate condition: n(r) = (1 − β)·Q for Policy 1, n(S) = (1 − β)·D·T
    for Policy 2. Returns ``(level, pinned)``; ``pinned`` is True when even the
    lowest level demand can take already meets it.
    """
    low = dist.support_low
    if math.isfinite(low) and target >= dist.loss(low):
        return low, True
    if dist.name == "Uniform":
        return dist.b - math.sqrt(2.0 * (dist.b - dist.a) * target), False
    if dist.name == "Exponential":
        return -math.log(dist.lam * target) / dist.lam, False
    if dist.name == "Normal":
        # G_u(k) = target/sigma; G_u falls from +inf to 0, so bisect on k.
        want = target / dist.sigma
        lo, hi = -1.0, 1.0
        while unit_normal_loss(lo) < want:
            lo *= 2.0
        while unit_normal_loss(hi) > want and hi < 64.0:
            hi *= 2.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if unit_normal_loss(mid) > want:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-14 * max(1.0, abs(mid)):
                break
        return dist.mu + 0.5 * (lo + hi) * dist.sigma, False
    if dist.discrete:
        # Smallest whole number with n(r) <= target; n only falls with r.
        _lo, hi_level, _cum, _surv, _loss = dist._tables()
        lo, hi = 0, hi_level
        while lo < hi:
            mid = (lo + hi) // 2
            if dist.loss(mid) <= target:
                hi = mid
            else:
                lo = mid + 1
        return float(lo), False
    raise SolverError(f"No fill-rate condition for {dist.name}.")


# --------------------------------------------------------------------------- #
#  Inputs, iterations, result
# --------------------------------------------------------------------------- #

@dataclass
class Inputs:
    """Problem data. All rates must share one time unit (year, week, ...)."""

    D: float                 # demand rate per unit time
    A: float                 # fixed cost per replenishment
    h: float                 # holding cost per unit per unit time
    p: float                 # penalty cost per unit short
    lead_time: float         # lead time, in the same unit
    dist: Distribution       # distribution of demand during the lead time
    v: float = 0.0           # unit purchase cost (shifts Y by a constant D·v)
    #: How running out is priced or bounded: "B2" (p per unit short, the
    #: default), "B1" (B1 per stockout occasion), "alpha" (cycle service
    #: level) or "beta" (fill rate). Only the field the basis names is read;
    #: p is ignored outside B2 and may then be 0.
    stockout: str = "B2"
    B1: float = 0.0          # cost per stockout occasion, for stockout="B1"
    alpha: float = 0.0       # P(no stockout in a cycle), for stockout="alpha"
    beta: float = 0.0        # fraction of demand met from stock, for "beta"

    def validate(self) -> None:
        if self.stockout not in STOCKOUT_MODES:
            raise SolverError(
                f"Unknown stockout basis {self.stockout!r}. Choose one of "
                + ", ".join(STOCKOUT_MODES) + ".")
        b2 = self.stockout == "B2"
        everything = [("demand rate D", self.D), ("ordering cost A", self.A),
                      ("holding cost h", self.h), ("penalty cost p", self.p),
                      ("lead time l", self.lead_time), ("unit cost v", self.v)]
        for label, value in everything:
            # NaN fails every comparison, so it has to be caught on its own.
            if not math.isfinite(value):
                raise SolverError(
                    f"The {label} must be an ordinary number; it is {value}.")
        for label, value in everything[:4]:
            if label.startswith("penalty") and not b2:
                continue
            if value <= 0.0:
                raise SolverError(f"The {label} must be greater than zero.")
        if self.lead_time < 0.0:
            raise SolverError("The lead time cannot be negative.")
        if self.v < 0.0:
            raise SolverError("The unit cost cannot be negative.")
        if not isinstance(self.dist, Distribution):
            raise SolverError("No lead-time demand distribution was given.")
        if self.stockout == "B1":
            if not math.isfinite(self.B1) or self.B1 <= 0.0:
                raise SolverError(
                    "The shortage cost per stockout occasion B1 must be a number "
                    "greater than zero.")
        for mode, symbol, word in (("alpha", "α", "cycle service level"),
                                   ("beta", "β", "fill rate")):
            if self.stockout == mode:
                value = getattr(self, mode)
                if not (math.isfinite(value) and 0.0 < value < 1.0):
                    raise SolverError(
                        f"The {word} {symbol} must be strictly between 0 and 1 "
                        f"(0.98 for 98 %); it is {value:g}.")

    @property
    def stockout_value(self) -> float:
        """The one number the stockout basis reads: p, B1, α or β."""
        return {"B2": self.p, "B1": self.B1,
                "alpha": self.alpha, "beta": self.beta}[self.stockout]

    @property
    def theta(self) -> float:
        """Expected lead-time demand D·l, as the cost function uses it."""
        return self.D * self.lead_time

    @property
    def eoq(self) -> float:
        return math.sqrt(2.0 * self.A * self.D / self.h)


@dataclass
class Iteration:
    #: The iteration number t, counted from 0 as the lecture does: iteration t
    #: starts from Q_t (Q_0 is the EOQ), finds r_t and n(r_t) from equation
    #: (2), and ends with Q_{t+1} from equation (1).
    index: int
    Q: float          # Q_t, the Q that entered this iteration
    tail: float       # 1 − G(r) = Q·h/(p·D)
    G_target: float   # G(r)
    r: float          # r_t from equation (2)
    n_r: float        # expected shortage per cycle at that r
    Q_next: float     # Q_{t+1} from equation (1)
    delta_r: float    # |r_t − r_{t−1}|, NaN in iteration 0
    #: B1 only: the density the reorder point has to reach, x = Q_t·h/(B1·D)
    #: from equation (2'). There ``tail`` is the 1 − G(r_t) that results and
    #: ``G_target`` the G(r_t), rather than targets r is read off. NaN otherwise.
    density_target: float = math.nan

    def as_row(self) -> list:
        return [self.index, self.Q, self.tail, self.G_target,
                self.r, self.n_r, self.Q_next, self.delta_r]


@dataclass
class Result:
    Q: float
    r: float
    n_r: float
    safety_stock: float
    iterations: list
    converged: bool
    inputs: Inputs
    notes: list = field(default_factory=list)
    #: True when equation (2) had no root and r had to be pinned, so the pair
    #: below is a fallback rather than a stationary point of the cost function.
    degenerate: bool = False
    #: True when the pinned case was reached only after the iteration ran away.
    diverged: bool = False
    #: True for the single-pass approximation: Q* is then Q_0 (the EOQ) and r*
    #: is r_0, rather than Q_{T+1} and r_T from the last iteration T.
    single_pass: bool = False

    # ---- cost breakdown at the solution -------------------------------- #
    @property
    def holding_cost(self) -> float:
        return self.inputs.h * (self.Q / 2.0 + self.r - self.inputs.theta)

    @property
    def ordering_cost(self) -> float:
        return self.inputs.A * self.inputs.D / self.Q

    @property
    def shortage_cost(self) -> float:
        """The stockout term of Y. A service level is a constraint, not a
        price, so under alpha and beta there is no such term and it is 0."""
        mode = self.inputs.stockout
        if mode == "B1":
            return self.inputs.B1 * self.inputs.D * self.stockout_probability / self.Q
        if mode != "B2":
            return 0.0
        return self.inputs.p * self.inputs.D * self.n_r / self.Q

    @property
    def stockout_probability(self) -> float:
        """1 − G(r*): the chance a replenishment cycle runs out."""
        return 1.0 - self.inputs.dist.cdf(self.r)

    @property
    def cycle_service_level(self) -> float:
        """G(r*): the chance a replenishment cycle does not run out (Type I)."""
        return self.inputs.dist.cdf(self.r)

    @property
    def cost_excluding_purchase(self) -> float:
        """Y without D·v — what the choice between policies turns on."""
        return self.holding_cost + self.ordering_cost + self.shortage_cost

    @property
    def purchase_cost(self) -> float:
        return self.inputs.D * self.inputs.v

    @property
    def total_cost(self) -> float:
        return (self.holding_cost + self.ordering_cost
                + self.shortage_cost + self.purchase_cost)

    @property
    def orders_per_period(self) -> float:
        return self.inputs.D / self.Q

    @property
    def cycle_length(self) -> float:
        return self.Q / self.inputs.D

    @property
    def fill_rate(self) -> float:
        """Fraction of demand met from stock, 1 − n(r)/Q, clamped to [0, 1].

        In the pinned case n(r) can exceed Q, which would make the raw ratio
        negative; a fill rate below zero is meaningless, so it reports 0.
        """
        if self.Q <= 0.0 or not math.isfinite(self.n_r):
            return 0.0
        return min(1.0, max(0.0, 1.0 - self.n_r / self.Q))

    def cost_breakdown(self) -> list:
        """(key, name, plain formula, value) per line of the cost."""
        rows = [("holding", "Holding cost", "h·(Q/2 + r − D·l)", self.holding_cost),
                ("ordering", "Ordering cost", "A·D/Q", self.ordering_cost)]
        mode = self.inputs.stockout
        if mode == "B2":
            rows.append(("shortage", "Shortage cost", "p·D·n(r)/Q", self.shortage_cost))
        elif mode == "B1":
            rows.append(("shortage", "Shortage cost", "B1·(D/Q)·(1 − G(r))",
                         self.shortage_cost))
        # alpha and beta: the service level is a constraint, so no shortage row.
        if self.inputs.v > 0.0:
            rows.append(("purchase", "Purchase cost", "D·v", self.purchase_cost))
        rows.append(("total", "Total cost", "Y(Q, r)", self.total_cost))
        return rows


# --------------------------------------------------------------------------- #
#  Solver
# --------------------------------------------------------------------------- #

def solve_rq(inputs: Inputs, tol: float = 1e-8, max_iter: int = 200,
             single_pass: bool = False) -> Result:
    """Iterate equations (1) and (2) until the reorder point stops moving.

    ``single_pass=True`` returns the deck's cost-effective approximation:
    Q = EOQ, then r from equation (2) alone.
    """
    inputs.validate()
    if max_iter < 1:
        raise SolverError("max_iter must be at least 1.")
    if inputs.stockout == "B1":
        return _solve_b1(inputs, tol, max_iter, single_pass)
    if inputs.stockout in ("alpha", "beta"):
        return _solve_service(inputs, single_pass)

    dist = inputs.dist
    notes: list = []
    iterations: list = []

    Q = inputs.eoq
    r_prev = math.nan
    converged = False
    degenerate = False
    diverged = False
    r = n_r = math.nan

    for i in range(1, max_iter + 1):
        tail = Q * inputs.h / (inputs.p * inputs.D)

        if tail >= 1.0:
            # Equation (2) has no root: a unit of shortage is cheaper than the
            # stock that would prevent it, so the cost keeps falling as r falls.
            degenerate = True
            diverged = i > 1
            bounded = math.isfinite(dist.support_low)
            r = dist.support_low if bounded else dist.mean
            n_r = dist.loss(r)
            Q_next = math.sqrt(2.0 * inputs.D * (inputs.A + inputs.p * n_r) / inputs.h)
            iterations.append(Iteration(i - 1, Q, tail, 1.0 - tail, r, n_r, Q_next,
                                        abs(r - r_prev) if i > 1 else math.nan))

            head = (f"Q·h/(p·D) = {tail:.3f} reached 1 in iteration {i - 1}, so "
                    "equation (2) has no root: the penalty cost p is too small "
                    "relative to the holding cost h.")
            if diverged:
                head += (" The iteration did not settle — Q grew on every pass "
                         "until the equation broke down.")
            if bounded:
                tail_note = (f" The reorder point is reported as {r:,.3f}, the "
                             "lowest level lead-time demand can take; no safety "
                             "stock is justified.")
            else:
                tail_note = (" Lead-time demand here has no lower bound, so the "
                             "cost has no finite minimum in r and there is no "
                             f"optimal reorder point. The mean, {r:,.3f}, is "
                             "reported only as a placeholder. Raise p, or state "
                             "a service level instead of a penalty cost.")
            notes.append(head + tail_note)

            if single_pass:
                Q = inputs.eoq
                notes.append(
                    "Single-pass approximation (slide 23): Q is left at the EOQ "
                    "and r comes from equation (2) only."
                )
            else:
                Q = Q_next
            break

        G_target = 1.0 - tail
        r = dist.inv_cdf(G_target)
        n_r = dist.loss(r)
        Q_next = math.sqrt(2.0 * inputs.D * (inputs.A + inputs.p * n_r) / inputs.h)
        delta_r = abs(r - r_prev) if i > 1 else math.nan
        iterations.append(Iteration(i - 1, Q, tail, G_target, r, n_r, Q_next,
                                    delta_r))

        if single_pass:
            notes.append(
                "Single-pass approximation (slide 23): Q is left at the EOQ and r "
                "comes from equation (2) only."
            )
            converged = True
            Q = inputs.eoq
            break

        if tol > 0 and i > 1 and abs(r - r_prev) <= tol and abs(Q_next - Q) <= tol:
            converged = True
            Q = Q_next
            break

        r_prev = r
        Q = Q_next
    else:
        if tol == 0:
            notes.append(f"Completed exactly {max_iter} passes (iteration 0 to "
                         f"{max_iter - 1}); tolerance 0 disables early convergence stopping.")
        else:
            notes.append(
                f"Stopped after {max_iter} iterations without meeting the tolerance "
                f"{tol:g}. The last reorder point moved by "
                f"{iterations[-1].delta_r:.3g}."
            )

    if dist.discrete:
        notes.append(
            "Lead-time demand is discrete, so r is the smallest integer whose "
            "cdf reaches the target; equation (2) holds as an inequality."
        )

    ss = r - inputs.theta
    if ss < 0.0 and not degenerate:
        notes.append(
            f"The safety stock is negative ({ss:,.3f}): the reorder point sits "
            "below expected lead-time demand. Check that D, the lead time and the "
            "distribution are stated in the same time unit."
        )

    return Result(Q=Q, r=r, n_r=n_r, safety_stock=ss, iterations=iterations,
                  converged=converged, inputs=inputs, notes=notes,
                  degenerate=degenerate, diverged=diverged,
                  single_pass=single_pass)


def _density_note(kind: str, dist: Distribution, x: float, level: float,
                  symbol: str, where: str) -> str | None:
    """What to say when the B1 condition g(level) = x had no interior root."""
    if kind == "root":
        return None
    if kind == "top":
        return (f"The Uniform density 1/(b − a) = {1.0 / (dist.b - dist.a):.6g} is "
                f"above {where} = {x:.6g} everywhere on [a, b], so the cost falls "
                f"all the way up to the corner {symbol} = b = {level:,.3f}: stocking "
                "the whole range is cheaper than risking a stockout occasion.")
    if kind == "global":
        return (f"Demand is discrete and its cost is not convex everywhere, so the "
                f"cheapest whole-number level, {level:,.0f}, sits below the "
                f"right-tail root of P(X = {symbol} + 1) <= {where}.")
    if dist.name == "Normal":
        return (f"The normal density never reaches {where} = {x:.6g}: "
                f"B1·D/(√(2π)·Q·h·σ) ≤ 1, so the condition has no root (slide 15, "
                f"step 1). Step 2 applies — set k at its lowest allowable value, "
                f"which management chooses. It is taken here as k = 0, "
                f"{symbol} = μ = {level:,.3f}; substitute your own floor if it differs.")
    if dist.name == "Uniform":
        return (f"The Uniform density 1/(b − a) = {1.0 / (dist.b - dist.a):.6g} does "
                f"not exceed {where} = {x:.6g}, so the cost rises with {symbol} "
                f"across [a, b] and the minimum is the corner {symbol} = a = "
                f"{level:,.3f}: no safety stock is justified.")
    return (f"The density never reaches {where} = {x:.6g} above zero, so the "
            f"condition has no root and {symbol} is pinned at {level:,.3f}, the "
            "lowest level demand can take: no safety stock is justified.")


def _solve_b1(inputs: Inputs, tol: float, max_iter: int,
              single_pass: bool) -> Result:
    """Cost B1 per stockout occasion: iterate (1') and (2') from the EOQ.

    (1')  Q = sqrt( 2·D·[A + B1·(1 − G(r))] / h )
    (2')  g(r) = Q·h / (B1·D),  root on the right tail

    The same rhythm as the B2 iteration — iteration t takes Q_t, reads r_t off
    (2'), and ends with Q_{t+1} from (1') — and single-pass stops at r_0 with Q
    left at the EOQ, which is slide 15 exactly.
    """
    dist = inputs.dist
    B1, D, h, A = inputs.B1, inputs.D, inputs.h, inputs.A
    notes: list = []
    iterations: list = []
    Q = inputs.eoq
    r_prev = math.nan
    converged = False
    kind = "root"
    x = r = n_r = math.nan

    for i in range(1, max_iter + 1):
        x = Q * h / (B1 * D)
        r, kind = _density_root(dist, x)
        G = dist.cdf(r)
        tail = 1.0 - G
        n_r = dist.loss(r)
        Q_next = math.sqrt(2.0 * D * (A + B1 * tail) / h)
        iterations.append(Iteration(i - 1, Q, tail, G, r, n_r, Q_next,
                                    abs(r - r_prev) if i > 1 else math.nan,
                                    density_target=x))
        if single_pass:
            notes.append("Single-pass approximation (slide 15): Q is left at the "
                         "EOQ and r comes from equation (2') only.")
            converged = True
            Q = inputs.eoq
            break
        if tol > 0 and i > 1 and abs(r - r_prev) <= tol and abs(Q_next - Q) <= tol:
            converged = True
            Q = Q_next
            break
        r_prev = r
        Q = Q_next
    else:
        if tol == 0:
            notes.append(f"Completed exactly {max_iter} passes (iteration 0 to "
                         f"{max_iter - 1}); tolerance 0 disables early convergence stopping.")
        else:
            notes.append(
                f"Stopped after {max_iter} iterations without meeting the tolerance "
                f"{tol:g}. The last reorder point moved by "
                f"{iterations[-1].delta_r:.3g}.")

    degenerate = kind == "floor"
    note = _density_note(kind, dist, x, r, "r", "Q·h/(B1·D)")
    if note:
        notes.insert(0, note)
    if dist.discrete:
        notes.append("Lead-time demand is discrete, so r is a whole number and "
                     "equation (2') holds as an inequality: P(X = r + 1) <= "
                     "Q·h/(B1·D).")
    ss = r - inputs.theta
    if ss < 0.0 and not degenerate:
        notes.append(
            f"The safety stock is negative ({ss:,.3f}): the reorder point sits "
            "below expected lead-time demand. Check that D, the lead time and the "
            "distribution are stated in the same time unit.")
    return Result(Q=Q, r=r, n_r=n_r, safety_stock=ss, iterations=iterations,
                  converged=converged, inputs=inputs, notes=notes,
                  degenerate=degenerate, diverged=False, single_pass=single_pass)


def _solve_service(inputs: Inputs, single_pass: bool) -> Result:
    """A service level instead of a price: Q = EOQ, then r alone.

    alpha:  G(r) = α                (cycle service level, Type I)
    beta:   n(r) = (1 − β)·Q        (fill rate, Type II)

    The textbook's sequential approach: Q is fixed at the EOQ first and r is
    set to meet the target, so there is nothing to iterate — one row.
    """
    dist = inputs.dist
    Q = inputs.eoq
    notes: list = []
    pinned = False
    if inputs.stockout == "alpha":
        r = dist.inv_cdf(inputs.alpha)
        notes.append(
            f"Cycle service level α = {inputs.alpha:g}: Q is the EOQ and r is the "
            f"α quantile of lead-time demand. There is no shortage cost term; "
            f"the fill rate this achieves, 1 − n(r)/Q, is "
            f"{min(1.0, max(0.0, 1.0 - dist.loss(r) / Q)):.3f}.")
        if dist.discrete:
            notes.append("Lead-time demand is discrete, so r is the smallest whole "
                         "number with G(r) >= α; the level achieved is "
                         f"{dist.cdf(r):.3f}.")
    else:
        target = (1.0 - inputs.beta) * Q
        r, pinned = _loss_root(dist, target)
        if pinned:
            notes.append(
                f"(1 − β)·Q = {target:,.6f} is at least the expected shortage at "
                f"the lowest level demand can take, n({r:g}) = {dist.loss(r):,.6f}, "
                f"so the fill rate is met with r = {r:,.3f} and no safety stock.")
        notes.append(
            f"Fill rate β = {inputs.beta:g}: Q is the EOQ and r makes the expected "
            "shortage per cycle n(r) equal (1 − β)·Q. There is no shortage cost "
            f"term; the chance a cycle runs out, 1 − G(r), is "
            f"{1.0 - dist.cdf(r):.3f}.")
        if dist.discrete:
            notes.append("Lead-time demand is discrete, so r is the smallest whole "
                         "number with n(r) <= (1 − β)·Q.")
    G = dist.cdf(r)
    n_r = dist.loss(r)
    it = Iteration(0, Q, 1.0 - G, G, r, n_r, Q, math.nan)
    ss = r - inputs.theta
    if ss < 0.0 and not pinned:
        notes.append(
            f"The safety stock is negative ({ss:,.3f}): the service level asked "
            "for is below what expected lead-time demand alone would give.")
    return Result(Q=Q, r=r, n_r=n_r, safety_stock=ss, iterations=[it],
                  converged=True, inputs=inputs, notes=notes,
                  degenerate=pinned, diverged=False, single_pass=single_pass)


# --------------------------------------------------------------------------- #
#  Policy 2 — periodic review (R, S)
# --------------------------------------------------------------------------- #

@dataclass
class PeriodicResult:
    """Order up to S every T: slides 46–52.

    Cost per base time unit (slide 49)::

        Y2(S) = A/T + h·(S − D·L − D·T/2) + [stockout term] + D·v

    The stockout term is p·n(S)/T under B2 and B1·(1 − G(S))/T under B1; a
    service level has none. n and G belong to demand over the protection
    interval T + L — ``protection`` — not to lead-time demand.
    """

    S: float
    n_S: float
    G_S: float
    T: float
    protection: Distribution
    #: (T + L)/L, the stretch applied to lead-time demand; NaN when the
    #: protection-interval demand was given directly.
    factor: float
    inputs: Inputs
    #: The right-hand side the basis solved: 1 − h·T/p (B2), h·T/B1 (B1),
    #: α (alpha) or (1 − β)·D·T (beta).
    target: float
    notes: list = field(default_factory=list)
    #: True when the condition had no root and S was pinned.
    degenerate: bool = False

    @property
    def mode(self) -> str:
        return self.inputs.stockout

    @property
    def protection_interval(self) -> float:
        return self.T + self.inputs.lead_time

    @property
    def safety_stock(self) -> float:
        return self.S - self.inputs.D * self.protection_interval

    @property
    def average_inventory(self) -> float:
        """S − D·L − D·T/2 (slide 48)."""
        return self.S - self.inputs.D * self.inputs.lead_time - self.inputs.D * self.T / 2.0

    @property
    def holding_cost(self) -> float:
        return self.inputs.h * self.average_inventory

    @property
    def ordering_cost(self) -> float:
        return self.inputs.A / self.T

    @property
    def shortage_cost(self) -> float:
        if self.mode == "B2":
            return self.inputs.p * self.n_S / self.T
        if self.mode == "B1":
            return self.inputs.B1 * (1.0 - self.G_S) / self.T
        return 0.0

    @property
    def purchase_cost(self) -> float:
        return self.inputs.D * self.inputs.v

    @property
    def cost_excluding_purchase(self) -> float:
        return self.holding_cost + self.ordering_cost + self.shortage_cost

    @property
    def total_cost(self) -> float:
        return self.cost_excluding_purchase + self.purchase_cost

    @property
    def orders_per_period(self) -> float:
        return 1.0 / self.T

    @property
    def stockout_probability(self) -> float:
        return 1.0 - self.G_S

    @property
    def fill_rate(self) -> float:
        """1 − n(S)/(D·T), clamped to [0, 1]: demand per review is D·T."""
        demand = self.inputs.D * self.T
        if demand <= 0.0 or not math.isfinite(self.n_S):
            return 0.0
        return min(1.0, max(0.0, 1.0 - self.n_S / demand))

    def cost_breakdown(self) -> list:
        """(key, name, plain formula, value) per line, as ``Result`` has it."""
        rows = [("holding", "Holding cost", "h·(S − D·L − D·T/2)", self.holding_cost),
                ("ordering", "Ordering cost", "A/T", self.ordering_cost)]
        if self.mode == "B2":
            rows.append(("shortage", "Shortage cost", "p·n(S)/T", self.shortage_cost))
        elif self.mode == "B1":
            rows.append(("shortage", "Shortage cost", "B1·(1 − G(S))/T",
                         self.shortage_cost))
        if self.inputs.v > 0.0:
            rows.append(("purchase", "Purchase cost", "D·v", self.purchase_cost))
        rows.append(("total", "Total cost", "Y2(S)", self.total_cost))
        return rows


def solve_periodic(inputs: Inputs, T: float,
                   protection: Distribution | None = None) -> PeriodicResult:
    """Policy 2: the order-up-to level S for a review every ``T``.

    ``T`` is in the base time unit, like the lead time. Demand over the
    protection interval T + L is lead-time demand scaled by f = (T + L)/L
    (:meth:`Distribution.scaled`), unless ``protection`` gives it directly —
    which is what slide 51 does (see the tests).

    The optimality condition by stockout basis, from dY2/dS = 0:

    B2     G(S) = 1 − h·T/p                 (slide 49)
    B1     g(S) = h·T/B1, right-tail root
    alpha  G(S) = α
    beta   n(S) = (1 − β)·D·T
    """
    inputs.validate()
    if not (isinstance(T, (int, float)) and math.isfinite(T)) or T <= 0.0:
        raise SolverError("The review period T must be a number greater than zero.")
    L = inputs.lead_time
    if protection is None:
        if L <= 0.0:
            raise SolverError(
                "Policy 2 gets demand over T + L by scaling lead-time demand by "
                "(T + L)/L, which needs a lead time greater than zero. Enter the "
                "lead time, or give the protection-interval demand directly.")
        factor = (T + L) / L
        protection = inputs.dist.scaled(factor)
    else:
        factor = math.nan
    dist = protection
    mode = inputs.stockout
    notes: list = []
    degenerate = False

    if mode == "B2":
        tail = inputs.h * T / inputs.p
        target = 1.0 - tail
        if tail >= 1.0:
            degenerate = True
            bounded = math.isfinite(dist.support_low)
            S = dist.support_low if bounded else dist.mean
            msg = (f"h·T/p = {tail:.3f} is at least 1, so G(S) = 1 − h·T/p has no "
                   "root: a unit short costs less than holding the stock that "
                   "would prevent it.")
            if bounded:
                msg += (f" S is reported as {S:,.3f}, the lowest level demand over "
                        "T + L can take.")
            else:
                msg += (" Demand over T + L has no lower bound, so there is no "
                        f"optimal S; its mean, {S:,.3f}, is only a placeholder. "
                        "Raise p, or state a service level instead.")
            notes.append(msg)
        else:
            S = dist.inv_cdf(target)
    elif mode == "B1":
        target = inputs.h * T / inputs.B1
        S, kind = _density_root(dist, target)
        degenerate = kind == "floor"
        note = _density_note(kind, dist, target, S, "S", "h·T/B1")
        if note:
            notes.append(note)
    elif mode == "alpha":
        target = inputs.alpha
        S = dist.inv_cdf(target)
    else:
        target = (1.0 - inputs.beta) * inputs.D * T
        S, degenerate = _loss_root(dist, target)
        if degenerate:
            notes.append(
                f"(1 − β)·D·T = {target:,.6f} is at least the expected shortage at "
                f"the lowest level demand can take, so S = {S:,.3f} already meets "
                "the fill rate.")

    if dist.discrete:
        notes.append("Demand over T + L is discrete, so S is a whole number and "
                     "its condition holds as an inequality.")
    res = PeriodicResult(S=S, n_S=dist.loss(S), G_S=dist.cdf(S), T=T,
                         protection=dist, factor=factor, inputs=inputs,
                         target=target, notes=notes, degenerate=degenerate)
    if res.average_inventory < 0.0 and not degenerate:
        notes.append(
            f"The average inventory S − D·L − D·T/2 is negative "
            f"({res.average_inventory:,.3f}): check that D, T, L and the demand "
            "distribution share one time unit.")
    return res


# --------------------------------------------------------------------------- #
#  Policy 1 against Policy 2
# --------------------------------------------------------------------------- #

@dataclass
class Comparison:
    """Both policies' cost per base time unit, on the same terms.

    ``policy1`` and ``policy2`` exclude the purchase cost D·v: it is the same
    for both (every unit demanded is bought either way), so it cannot change
    which is cheaper. ``purchase`` carries it for display.
    """

    policy1: float
    policy2: float
    purchase: float
    #: "Policy 1", "Policy 2", or "Either" when they tie.
    chosen: str
    #: |Y1 − Y2|, the saving from choosing the cheaper one.
    difference: float
    notes: list = field(default_factory=list)

    @property
    def policy1_total(self) -> float:
        return self.policy1 + self.purchase

    @property
    def policy2_total(self) -> float:
        return self.policy2 + self.purchase


def compare_policies(res1: Result, res2: PeriodicResult) -> Comparison:
    """Name the cheaper of continuous review (r, Q) and periodic review (R, S)."""
    y1 = res1.cost_excluding_purchase
    y2 = res2.cost_excluding_purchase
    diff = abs(y1 - y2)
    if diff <= 1e-9 * max(1.0, abs(y1), abs(y2)):
        chosen = "Either"
    else:
        chosen = "Policy 1" if y1 < y2 else "Policy 2"
    notes = []
    purchase = res1.purchase_cost
    if purchase > 0.0:
        notes.append(f"Both include the same purchase cost D·v = {purchase:,.3f}; "
                     "it does not affect the choice, so the comparison leaves it out.")
    if res1.inputs.stockout in ("alpha", "beta"):
        notes.append("Under a service level neither cost has a shortage term: the "
                     "comparison is holding plus ordering at the same service.")
    if res1.degenerate or res2.degenerate:
        notes.append("At least one policy had no interior optimum and was pinned "
                     "(see its notes), so read the comparison with care.")
    return Comparison(policy1=y1, policy2=y2, purchase=purchase, chosen=chosen,
                      difference=diff, notes=notes)


# --------------------------------------------------------------------------- #
#  Lecture-deck regression cases (slides 25-40). Used only by the tests to pin
#  the solver against the deck's worked answers; not shown in any front end.
# --------------------------------------------------------------------------- #

DECK_EXAMPLES = {
    "Slide 25 — air filters, Uniform(0, 200)": dict(
        D=800.0, A=10.0, h=2.0, p=5.0, lead_time=2.0 / 52.0, v=25.0,
        base_unit="year", lead_unit="week", lead_value=2.0,
        dist_name="Uniform", dist_params={"a": 0.0, "b": 200.0},
        expected="Deck answer (Q*, r*) = (94, 190). Carried at full precision the "
                 "fixed point is (94.2809, 190.5719): Q = sqrt(80000/9). The deck's "
                 "190 comes from rounding r to a whole unit at each step.",
    ),
    "Slide 32 — same data, Exponential(mean 100)": dict(
        D=800.0, A=10.0, h=2.0, p=5.0, lead_time=2.0 / 52.0, v=25.0,
        base_unit="year", lead_unit="week", lead_value=2.0,
        dist_name="Exponential", dist_params={"mean": 100.0},
        expected="Deck stops before converging; the fixed point is (234.16, 214.50)",
    ),
    "Slide 34 — weekly demand, Normal(80, 4)": dict(
        D=40.0, A=50.0, h=0.0225, p=5.0, lead_time=2.0, v=0.0,
        base_unit="week", lead_unit="week", lead_value=2.0,
        dist_name="Normal", dist_params={"mu": 80.0, "sigma": 4.0},
        expected="Deck answer (Q*, r*) = (423.3, 86.68)",
    ),
    "Slide 40 — practice, weekly demand N(35, 8)": dict(
        D=35.0, A=50.0, h=0.0225, p=5.0, lead_time=2.0, v=0.0,
        base_unit="week", lead_unit="week", lead_value=2.0,
        dist_name="Normal", dist_params={"mu": 70.0, "sigma": 4.0},
        expected="No solution printed in the deck",
    ),
}


# --------------------------------------------------------------------------- #
#  Built-in problems the front ends offer to load (web, terminal, desktop):
#  the two Homework 2 problems only.
# --------------------------------------------------------------------------- #

EXAMPLES = {
    # ----------------------------------------------------------------------- #
    # Homework 2. Neither problem states h or the lead-time distribution: both
    # give a carrying charge against the unit cost and demand per period, so
    # the numbers below are the result of `derive`, written out as the closed
    # forms they come from rather than as decimals that could drift from it.
    # `test_rq_solver` holds the two in step.
    # ----------------------------------------------------------------------- #
    "Homework 2, Problem 1 — IEM, monthly N(28, 8²)": dict(
        D=12.0 * 28.0, A=15.0, h=6.0 * 0.3, p=7.0, lead_time=14.0 / 52.0, v=6.0,
        base_unit="year", lead_unit="week", lead_value=14.0,
        dist_name="Normal",
        dist_params={"mu": 28.0 * (14.0 / 52.0 * 12.0),
                     "sigma": 8.0 * math.sqrt(14.0 / 52.0 * 12.0)},
        derive={
            "holding": {"mode": "rate", "v": 6.0, "carrying_rate": 0.3,
                        "rate_unit": "year"},
            "demand": {"mode": "period", "mean": 28.0, "sigma": 8.0,
                       "period_unit": "month"},
        },
        expected="Manual solution: theta = 90.462, sigma = 14.379, and after "
                 "convergence (Q*, r*) = (81.323, 112.552) with 22.091 units "
                 "of safety stock. The question asks for iterations 0, 1 and 2 — "
                 "set the iteration cap to 3.",
    ),
    "Homework 2, Problem 2 — computers, weekly N(100, 3²)": dict(
        D=100.0, A=200.0, h=40.0 * 0.1, p=30.0, lead_time=2.0, v=40.0,
        base_unit="week", lead_unit="week", lead_value=2.0,
        dist_name="Normal",
        dist_params={"mu": 100.0 * 2.0, "sigma": 3.0 * math.sqrt(2.0)},
        derive={
            "holding": {"mode": "rate", "v": 40.0, "carrying_rate": 0.1,
                        "rate_unit": "week"},
            "demand": {"mode": "period", "mean": 100.0, "sigma": 3.0,
                       "period_unit": "week"},
        },
        expected="Manual solution: theta = 200.000, sigma = 4.243, and the fixed "
                 "point is (Q*, r*) = (102.171, 204.656) with 4.656 units of "
                 "safety stock.",
    ),
}


# --------------------------------------------------------------------------- #
# Homework 2, Problem 3 — an ophthalmologist's office, three products, two
# scenarios each. Weeks are the base unit (52 to the year); A = $54 an order;
# carrying charge 25 %/year; lead time 3 weeks; Policy 2 reviews monthly.
#
#   Scenario 1  "safety stock can meet 98 % of demand during lead time": read
#               as a cycle service level, alpha = 0.98 (P(no stockout in a
#               cycle)) — the lead's benchmark table was computed that way.
#   Scenario 2  backorder cost per unit = 30 % of the unit price: B2 with
#               p = 0.30·v, worked out by the `penalty` derivation.
#
# Every entry also carries p = 0.30·v inline, so an interface that knows only
# the B2 model (the Tkinter app) still has a complete problem to solve; under
# Scenario 1 the stockout block overrides it and p is never read.
#
# Lead-time demand comes from demand per week over k = 3 weeks: Normal exactly
# (theta = 3μ, sigma = s·sqrt 3), Uniform and Exponential by the lecture's
# simplification of scaling the bounds / the mean (a sum of uniforms is not
# uniform, nor a sum of exponentials exponential). `test_policies` holds the
# inline numbers to `derive`.
# --------------------------------------------------------------------------- #

_P3_COMMON = dict(A=54.0, lead_time=3.0, base_unit="week", lead_unit="week",
                  lead_value=3.0, periodic={"T": 1.0, "T_unit": "month"})

_P3_PRODUCTS = [
    # (name in the key, distribution words, v, D per week, lead-time law,
    #  lead-time params, per-week demand block)
    ("blue masks", "weekly N(90, 15²)", 7.0, 90.0, "Normal",
     {"mu": 90.0 * 3.0, "sigma": 15.0 * math.sqrt(3.0)},
     {"mode": "period", "dist": "Normal", "mean": 90.0, "sigma": 15.0,
      "period_unit": "week"}),
    ("sanitizer dispensers", "weekly U(0.25, 1)", 40.0, (0.25 + 1.0) / 2.0,
     "Uniform", {"a": 0.25 * 3.0, "b": 1.0 * 3.0},
     {"mode": "period", "dist": "Uniform", "lo": 0.25, "hi": 1.0,
      "period_unit": "week"}),
    # "Mean occurrence time λ = 10 weeks per unit": one gown every 10 weeks,
    # so D = 0.1 per week and lead-time demand is Exponential(mean 0.3).
    ("sterile gowns", "Exponential, one per 10 weeks", 400.0, 0.1, "Exponential",
     {"mean": 0.1 * 3.0},
     {"mode": "period", "dist": "Exponential", "mean": 0.1,
      "period_unit": "week"}),
]

#: Policy 1 then Policy 2, per week, costs excluding D·v — what `expected` says.
_P3_ANSWERS = {
    ("blue masks", 1): "Policy 1: (Q*, r*) = (537.4224, 323.3580), SS 53.3580, "
                       "19.8820/wk (1,033.87/yr). Policy 2: S = 743.4237, SS 83.4237, "
                       "21.8316/wk (1,135.24/yr). Choose Policy 1.",
    ("blue masks", 2): "Policy 1: (Q*, r*) = (549.8093, 303.6089), SS 33.6089, "
                       "19.6343/wk. Policy 2: S = 720.1155, SS 60.1155, 21.6510/wk. "
                       "Choose Policy 1.",
    ("sanitizer dispensers", 1): "Policy 1: (Q*, r*) = (18.7350, 2.9550), SS 1.0800, "
                                 "3.8106/wk (198.15/yr). Policy 2: S = 7.2233, "
                                 "SS 2.6400, 13.2296/wk (687.94/yr). Choose Policy 1.",
    ("sanitizer dispensers", 2): "Policy 1: (Q*, r*) = (19.3000, 1.8865), SS 0.0115, "
                                 "3.7138/wk. Policy 2: S = 6.9514, SS 2.3681, "
                                 "13.2141/wk. Choose Policy 1.",
    ("sterile gowns", 1): "Policy 1: (Q*, r*) = (2.3698, 1.1736), SS 0.8736, "
                          "6.2373/wk (324.34/yr). Policy 2: S = 2.8688, SS 2.1355, "
                          "16.9849/wk (883.22/yr). Choose Policy 1.",
    ("sterile gowns", 2): "Policy 1: (Q*, r*) = (2.6887, 0.2526), SS −0.0474, "
                          "5.0794/wk. Policy 2: S = 1.9560, SS 1.2226, 16.6397/wk. "
                          "Choose Policy 1.",
}

for _name, _words, _v, _D, _dist, _params, _demand in _P3_PRODUCTS:
    for _scenario in (1, 2):
        _derive = {
            "holding": {"mode": "rate", "v": _v, "carrying_rate": 0.25,
                        "rate_unit": "year"},
            "demand": dict(_demand),
        }
        if _scenario == 1:
            _label = "Scenario 1 (98% service)"
            _stockout = {"mode": "alpha", "value": 0.98}
        else:
            _label = "Scenario 2 (backorder 30% of v)"
            _stockout = {"mode": "B2"}
            _derive["penalty"] = {"mode": "fraction", "b": 0.30}
        EXAMPLES[f"Homework 2, Problem 3 — {_name}, {_label}"] = dict(
            _P3_COMMON, D=_D, h=_v * 0.25 / 52.0, p=0.30 * _v, v=_v,
            dist_name=_dist, dist_params=dict(_params), derive=_derive,
            stockout=_stockout, periodic=dict(_P3_COMMON["periodic"]),
            expected=f"{_words}. " + _P3_ANSWERS[(_name, _scenario)],
        )
del (_name, _words, _v, _D, _dist, _params, _demand, _scenario, _derive,
     _label, _stockout)


def example_inputs(key: str) -> Inputs:
    """Build :class:`Inputs` for a built-in problem.

    ``key`` names an entry of :data:`EXAMPLES` (the homework problems) or of
    :data:`DECK_EXAMPLES` (the test-only lecture-deck cases). An entry with a
    ``stockout`` block gets that basis; every other one is B2 with its own p.
    """
    spec = EXAMPLES[key] if key in EXAMPLES else DECK_EXAMPLES[key]
    dist = build_distribution(spec["dist_name"], spec["dist_params"])
    inp = Inputs(D=spec["D"], A=spec["A"], h=spec["h"], p=spec["p"],
                 lead_time=spec["lead_time"], dist=dist, v=spec["v"])
    stockout = spec.get("stockout") or {}
    mode = stockout.get("mode", "B2")
    if mode != "B2":
        inp.stockout = mode
        setattr(inp, mode, float(stockout["value"]))
    return inp


def example_review_period(key: str) -> float | None:
    """Policy 2's review period T for a built-in problem, in its base unit.

    ``None`` when the problem has no periodic review. The entry states T in a
    unit of its own (Problem 3: one month), converted on the lecture calendar.
    """
    spec = EXAMPLES[key] if key in EXAMPLES else DECK_EXAMPLES[key]
    periodic = spec.get("periodic")
    if not periodic:
        return None
    from timeunits import convert      # timeunits imports this module
    base = spec.get("base_unit", "year")
    return convert(float(periodic["T"]), periodic.get("T_unit") or base, base)
