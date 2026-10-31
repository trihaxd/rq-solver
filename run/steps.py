"""Any iteration written out: formula, numbers in, result.

Iterations are counted from 0, as in the lecture and the manual solution:
iteration t starts from Q_t (Q_0 is the EOQ), reads r_t off equation (2),
computes the loss n(r_t), and ends with Q_{t+1} from equation (1). Every
subscript below follows that one rule.

The quantile and the loss function differ for every lead-time demand
distribution, so this is built where the distribution is known rather than in
the page. Each step carries TeX for KaTeX and a plain spelling for when KaTeX
cannot load.
"""

from __future__ import annotations

import math
from dataclasses import replace

from rq_solver import Inputs, Iteration

__all__ = ["first_pass_steps", "pass_steps", "periodic_steps",
           "density_root_steps"]


def g(x: float) -> str:
    """An input roughly as it was typed: 0.0225, 50, 0.038462."""
    return f"{x:.6g}"


def n(x: float, dp: int = 3) -> str:
    return f"{x:.3f}"


def _opening(inp: Inputs, it: Iteration, t: int) -> dict:
    """Where iteration t gets its Q: the EOQ in iteration 0, the Q that
    iteration t − 1 ended with in every later one."""
    if t == 0:
        return {
            "label": "Iteration 0 starts at the EOQ",
            "tex": (r"Q_0=\sqrt{\dfrac{2AD}{h}}"
                    rf"=\sqrt{{\dfrac{{2({g(inp.A)})({g(inp.D)})}}{{{g(inp.h)}}}}}"
                    rf"={n(it.Q)}"),
            "plain": (f"Q0 = sqrt(2AD/h) = sqrt(2({g(inp.A)})({g(inp.D)})"
                      f"/{g(inp.h)}) = {n(it.Q)}"),
        }
    return {
        "label": (f"Iteration {t} starts from Q{t}, the order quantity "
                  f"iteration {t - 1} ended with"),
        "tex": rf"Q_{{{t}}}={n(it.Q)}",
        "plain": f"Q{t} = {n(it.Q)}",
    }


def _tail(inp: Inputs, it: Iteration, t: int) -> dict:
    return {
        "label": "Equation (2): the share of the distribution above r",
        "tex": (rf"1-G(r_{{{t}}})=\dfrac{{Q_{{{t}}}\,h}}{{p\,D}}"
                rf"=\dfrac{{({n(it.Q)})({g(inp.h)})}}"
                rf"{{({g(inp.p)})({g(inp.D)})}}={n(it.tail, 6)}"),
        "plain": (f"1 - G(r{t}) = Q{t}·h / (p·D) = ({n(it.Q)})({g(inp.h)})"
                  f" / (({g(inp.p)})({g(inp.D)})) = {n(it.tail, 6)}"),
    }


def _cdf(it: Iteration, t: int) -> dict:
    return {
        "label": "so the cdf at the reorder point is",
        "tex": rf"G(r_{{{t}}})=1-{n(it.tail, 6)}={n(it.G_target, 6)}",
        "plain": f"G(r{t}) = 1 - {n(it.tail, 6)} = {n(it.G_target, 6)}",
    }


def _normal(dist, it: Iteration, t: int) -> list:
    z = (it.r - dist.mu) / dist.sigma
    loss = it.n_r / dist.sigma if dist.sigma else 0.0
    return [
        {"label": "Read the safety factor off the standard normal",
         "tex": rf"z_{{{t}}}=\Phi^{{-1}}({n(it.G_target, 6)})={n(z, 5)}",
         "plain": f"z{t} = inverse normal of {n(it.G_target, 6)} = {n(z, 5)}"},
        {"label": "Reorder point",
         "tex": (rf"r_{{{t}}}=\mu+z_{{{t}}}\,\sigma"
                 rf"={g(dist.mu)}+({n(z, 5)})({g(dist.sigma)})={n(it.r)}"),
         "plain": (f"r{t} = mu + z{t}·sigma = {g(dist.mu)} + ({n(z, 5)})"
                   f"({g(dist.sigma)}) = {n(it.r)}")},
        {"label": "Expected shortage per cycle, via the unit normal loss function",
         "tex": (rf"n(r_{{{t}}})=\sigma\,G_u(z_{{{t}}})"
                 rf"=({g(dist.sigma)})({n(loss, 6)})={n(it.n_r, 6)}"),
         "plain": (f"n(r{t}) = sigma·Gu(z{t}) = ({g(dist.sigma)})({n(loss, 6)})"
                   f" = {n(it.n_r, 6)}")},
    ]


def _uniform(dist, it: Iteration, t: int) -> list:
    return [
        {"label": "Reorder point, from the uniform quantile",
         "tex": (rf"r_{{{t}}}=a+G(r_{{{t}}})\,(b-a)"
                 rf"={g(dist.a)}+({n(it.G_target, 6)})({g(dist.b)}-{g(dist.a)})"
                 rf"={n(it.r)}"),
         "plain": (f"r{t} = a + G(r{t})(b - a) = {g(dist.a)} + ({n(it.G_target, 6)})"
                   f"({g(dist.b)} - {g(dist.a)}) = {n(it.r)}")},
        {"label": "Expected shortage per cycle",
         "tex": (rf"n(r_{{{t}}})=\dfrac{{(b-r_{{{t}}})^2}}{{2(b-a)}}"
                 rf"=\dfrac{{({g(dist.b)}-{n(it.r)})^2}}"
                 rf"{{2({g(dist.b)}-{g(dist.a)})}}={n(it.n_r, 6)}"),
         "plain": (f"n(r{t}) = (b - r{t})^2 / (2(b - a)) = ({g(dist.b)} - {n(it.r)})^2"
                   f" / (2({g(dist.b)} - {g(dist.a)})) = {n(it.n_r, 6)}")},
    ]


def _exponential(dist, it: Iteration, t: int) -> list:
    return [
        {"label": "Reorder point, from the exponential quantile",
         "tex": (rf"r_{{{t}}}=-\dfrac{{\ln(1-G(r_{{{t}}}))}}{{\lambda}}"
                 rf"=-\dfrac{{\ln({n(it.tail, 6)})}}{{{g(dist.lam)}}}={n(it.r)}"),
         "plain": (f"r{t} = -ln(1 - G(r{t})) / lambda = -ln({n(it.tail, 6)})"
                   f" / {g(dist.lam)} = {n(it.r)}")},
        {"label": "Expected shortage per cycle",
         "tex": (rf"n(r_{{{t}}})=\dfrac{{e^{{-\lambda r_{{{t}}}}}}}{{\lambda}}"
                 rf"=\dfrac{{{n(it.tail, 6)}}}{{{g(dist.lam)}}}={n(it.n_r, 6)}"),
         "plain": (f"n(r{t}) = e^(-lambda·r{t}) / lambda = {n(it.tail, 6)}"
                   f" / {g(dist.lam)} = {n(it.n_r, 6)}")},
    ]


def _discrete(it: Iteration, t: int) -> list:
    return [
        {"label": "Reorder point: the smallest whole number reaching that cdf",
         "tex": (rf"r_{{{t}}}=\min\{{\,k\in\mathbb{{Z}}: G(k)\ge "
                 rf"{n(it.G_target, 6)}\,\}}={n(it.r, 0)}"),
         "plain": (f"r{t} = smallest integer k with G(k) >= {n(it.G_target, 6)}"
                   f" = {n(it.r, 0)}")},
        {"label": "Expected shortage per cycle",
         "tex": (rf"n(r_{{{t}}})=\sum_{{x\ge r_{{{t}}}}}(x-r_{{{t}}})\,P(X=x)="
                 rf"{n(it.n_r, 6)}"),
         "plain": (f"n(r{t}) = sum over x >= r{t} of (x - r{t})P(X = x)"
                   f" = {n(it.n_r, 6)}")},
    ]


def _next_q(inp: Inputs, it: Iteration, t: int) -> dict:
    return {
        "label": f"Equation (1): the new order quantity, Q{t + 1}",
        "tex": (rf"Q_{{{t + 1}}}=\sqrt{{\dfrac{{2D[A+p\,n(r_{{{t}}})]}}{{h}}}}"
                rf"=\sqrt{{\dfrac{{2({g(inp.D)})[{g(inp.A)}+({g(inp.p)})"
                rf"({n(it.n_r, 6)})]}}{{{g(inp.h)}}}}}={n(it.Q_next)}"),
        "plain": (f"Q{t + 1} = sqrt(2D[A + p·n(r{t})] / h) = sqrt(2({g(inp.D)})"
                  f"[{g(inp.A)} + ({g(inp.p)})({n(it.n_r, 6)})] / {g(inp.h)})"
                  f" = {n(it.Q_next)}"),
    }


def _movement(it: Iteration, t: int) -> dict:
    return {
        "label": "How far the reorder point moved",
        "tex": (rf"|\Delta r|=|r_{{{t}}}-r_{{{t - 1}}}|={n(it.delta_r, 8)}"),
        "plain": f"|delta r| = |r{t} - r{t - 1}| = {n(it.delta_r, 8)}",
    }


def pass_steps(inp: Inputs, it: Iteration, t: int | None = None) -> list:
    """Every line of iteration ``t`` (counted from 0), in the order it is worked.

    ``t`` defaults to ``it.index`` and only sets the subscripts and the opening
    line; the arithmetic shown is whatever ``it`` recorded, so the walkthrough
    cannot drift from the table.
    """
    if t is None:
        t = it.index
    dist = inp.dist
    if inp.stockout == "B1":
        return _b1_steps(inp, it, t)
    if inp.stockout == "alpha":
        return _alpha_steps(inp, it)
    if inp.stockout == "beta":
        return _beta_steps(inp, it)
    steps = [_opening(inp, it, t), _tail(inp, it, t), _cdf(it, t)]
    if dist.name == "Normal":
        steps += _normal(dist, it, t)
    elif dist.name == "Uniform":
        steps += _uniform(dist, it, t)
    elif dist.name == "Exponential":
        steps += _exponential(dist, it, t)
    else:
        steps += _discrete(it, t)
    steps.append(_next_q(inp, it, t))
    if t > 0:
        steps.append(_movement(it, t))
    return steps


def first_pass_steps(inp: Inputs, it: Iteration) -> list:
    """Every line of iteration 0, in the order it is worked."""
    return pass_steps(inp, it, 0)


# --------------------------------------------------------------------------- #
#  Stockout cost B1 per occasion: (2') g(r) = Q·h/(B1·D), (1') for Q
# --------------------------------------------------------------------------- #

def _density(inp: Inputs, it: Iteration, t: int) -> dict:
    return {
        "label": "Equation (2'): the density of demand at the reorder point",
        "tex": (rf"g(r_{{{t}}})=\dfrac{{Q_{{{t}}}\,h}}{{B_1\,D}}"
                rf"=\dfrac{{({n(it.Q)})({g(inp.h)})}}"
                rf"{{({g(inp.B1)})({g(inp.D)})}}={n(it.density_target, 6)}"),
        "plain": (f"g(r{t}) = Q{t}·h / (B1·D) = ({n(it.Q)})({g(inp.h)})"
                  f" / (({g(inp.B1)})({g(inp.D)})) = {n(it.density_target, 6)}"),
    }


def density_root_steps(dist, x: float, level: float, sym: str,
                       x_tex: str, x_plain: str) -> list:
    """Solve g(level) = x on the right tail, per distribution.

    Shared by Policy 1 (``sym`` = r_t, x = Q·h/(B1·D)) and Policy 2 (``sym`` = S,
    x = h·T/B1). ``level`` is the value the solver found; the steps show how.
    """
    if dist.name == "Normal":
        arg = 1.0 / (x * dist.sigma * math.sqrt(2.0 * math.pi))
        steps = [{
            "label": "Slide 15, step 1: does the normal density reach that height?",
            "tex": (rf"\dfrac{{1}}{{{x_tex}\,\sigma\sqrt{{2\pi}}}}"
                    rf"=\dfrac{{1}}{{({n(x, 6)})({g(dist.sigma)})\sqrt{{2\pi}}}}"
                    rf"={n(arg, 6)}"),
            "plain": (f"1 / ({x_plain}·sigma·sqrt(2pi)) = 1 / (({n(x, 6)})"
                      f"({g(dist.sigma)})sqrt(2pi)) = {n(arg, 6)}"),
        }]
        k = (level - dist.mu) / dist.sigma
        if arg > 1.0:
            steps.append({
                "label": "It is above 1, so there is a root: the safety factor",
                "tex": rf"k=\sqrt{{2\ln({n(arg, 6)})}}={n(k, 5)}",
                "plain": f"k = sqrt(2·ln({n(arg, 6)})) = {n(k, 5)}",
            })
        else:
            steps.append({
                "label": ("At most 1, so no root (slide 15, step 2): k goes to its "
                          "lowest allowable value, taken as 0"),
                "tex": r"k=0",
                "plain": "k = 0 (management's floor)",
            })
        steps.append({
            "label": "The level itself",
            "tex": (rf"{sym}=\mu+k\,\sigma={g(dist.mu)}+({n(k, 5)})({g(dist.sigma)})"
                    rf"={n(level)}"),
            "plain": (f"{sym} = mu + k·sigma = {g(dist.mu)} + ({n(k, 5)})"
                      f"({g(dist.sigma)}) = {n(level)}"),
        })
        return steps
    if dist.name == "Exponential":
        if x >= dist.lam:
            return [{
                "label": (f"The density never exceeds lambda = {g(dist.lam)}, which "
                          "is not above that height: no root, the level is pinned at 0"),
                "tex": rf"{x_tex}={n(x, 6)}\ge\lambda\ \Rightarrow\ {sym}=0",
                "plain": f"{x_plain} = {n(x, 6)} >= lambda, so {sym} = 0",
            }]
        return [{
            "label": "Solve the exponential density for the level",
            "tex": (rf"\lambda e^{{-\lambda {sym}}}={x_tex}\ \Rightarrow\ "
                    rf"{sym}=\dfrac{{\ln(\lambda/{x_tex})}}{{\lambda}}"
                    rf"=\dfrac{{\ln({g(dist.lam)}/{n(x, 6)})}}{{{g(dist.lam)}}}"
                    rf"={n(level)}"),
            "plain": (f"lambda·e^(-lambda·{sym}) = {x_plain}, so {sym} = "
                      f"ln(lambda/{x_plain})/lambda = ln({g(dist.lam)}/{n(x, 6)})"
                      f"/{g(dist.lam)} = {n(level)}"),
        }]
    if dist.name == "Uniform":
        flat = 1.0 / (dist.b - dist.a)
        above = x < flat
        return [{
            "label": ("A flat density, so the cost is linear in the level and the "
                      "answer is a corner: " + ("the top, b" if above else
                                                "the bottom, a — no safety stock")),
            "tex": (rf"\tfrac{{1}}{{b-a}}={n(flat, 6)}"
                    + (r"\ >\ " if above else r"\ \le\ ")
                    + rf"{x_tex}={n(x, 6)}\ \Rightarrow\ {sym}={n(level)}"),
            "plain": (f"1/(b - a) = {n(flat, 6)} " + (">" if above else "<=")
                      + f" {x_plain} = {n(x, 6)}, so {sym} = {n(level)}"),
        }]
    return [{
        "label": ("Discrete demand: the smallest whole number at or past the mode "
                  "where the next probability falls to that height"),
        "tex": (rf"{sym}=\min\{{\,k\ge\lfloor\lambda\rfloor: P(X=k+1)\le "
                rf"{n(x, 6)}\,\}}={n(level, 0)}"),
        "plain": (f"{sym} = smallest k >= floor(lambda) with P(X = k + 1) <= "
                  f"{n(x, 6)} = {n(level, 0)}"),
    }]


def _b1_steps(inp: Inputs, it: Iteration, t: int) -> list:
    steps = [_opening(inp, it, t), _density(inp, it, t)]
    steps += density_root_steps(inp.dist, it.density_target, it.r, f"r_{{{t}}}",
                                r"\tfrac{Q h}{B_1 D}", "Q·h/(B1·D)")
    # The TeX subscripts above use r_{t}; the plain spelling wants r{t}.
    for step in steps[2:]:
        step["plain"] = step["plain"].replace(f"r_{{{t}}}", f"r{t}")
    steps += [
        {"label": "The chance a cycle runs out at that reorder point",
         "tex": rf"1-G(r_{{{t}}})={n(it.tail, 6)}",
         "plain": f"1 - G(r{t}) = {n(it.tail, 6)}"},
        {"label": f"Equation (1'): the new order quantity, Q{t + 1}",
         "tex": (rf"Q_{{{t + 1}}}=\sqrt{{\dfrac{{2D[A+B_1(1-G(r_{{{t}}}))]}}{{h}}}}"
                 rf"=\sqrt{{\dfrac{{2({g(inp.D)})[{g(inp.A)}+({g(inp.B1)})"
                 rf"({n(it.tail, 6)})]}}{{{g(inp.h)}}}}}={n(it.Q_next)}"),
         "plain": (f"Q{t + 1} = sqrt(2D[A + B1·(1 - G(r{t}))] / h) = sqrt(2({g(inp.D)})"
                   f"[{g(inp.A)} + ({g(inp.B1)})({n(it.tail, 6)})] / {g(inp.h)})"
                   f" = {n(it.Q_next)}")},
    ]
    if t > 0:
        steps.append(_movement(it, t))
    return steps


# --------------------------------------------------------------------------- #
#  Service levels: Q = EOQ, then r alone
# --------------------------------------------------------------------------- #

def _eoq(inp: Inputs, it: Iteration) -> dict:
    return {
        "label": "Q is the EOQ: a service level sets r, not Q",
        "tex": (r"Q=\sqrt{\dfrac{2AD}{h}}"
                rf"=\sqrt{{\dfrac{{2({g(inp.A)})({g(inp.D)})}}{{{g(inp.h)}}}}}"
                rf"={n(it.Q)}"),
        "plain": (f"Q = sqrt(2AD/h) = sqrt(2({g(inp.A)})({g(inp.D)})"
                  f"/{g(inp.h)}) = {n(it.Q)}"),
    }


def _alpha_steps(inp: Inputs, it: Iteration) -> list:
    dist = inp.dist
    steps = [_eoq(inp, it), {
        "label": "Cycle service level: the cdf at the reorder point is α",
        "tex": rf"G(r)=\alpha={g(inp.alpha)}",
        "plain": f"G(r) = alpha = {g(inp.alpha)}",
    }]
    # The row records the G(r) reached; the quantile is read at α itself (they
    # differ only for discrete demand, where G jumps past α).
    at = replace(it, G_target=inp.alpha, tail=1.0 - inp.alpha)
    if dist.name == "Normal":
        rows = _normal(dist, at, 0)
    elif dist.name == "Uniform":
        rows = _uniform(dist, at, 0)
    elif dist.name == "Exponential":
        rows = _exponential(dist, at, 0)
    else:
        rows = _discrete(at, 0)
    # The quantile rows were written for equation (2); here the cdf target is α.
    for row in rows:
        row["tex"] = row["tex"].replace("r_{0}", "r").replace("z_{0}", "z")
        row["plain"] = row["plain"].replace("r0", "r").replace("z0", "z")
    steps += rows
    fill = min(1.0, max(0.0, 1.0 - it.n_r / it.Q))
    steps.append({
        "label": "The fill rate this gives, for information",
        "tex": (rf"1-\dfrac{{n(r)}}{{Q}}=1-\dfrac{{{n(it.n_r, 6)}}}{{{n(it.Q)}}}"
                rf"={n(fill, 6)}"),
        "plain": f"1 - n(r)/Q = 1 - {n(it.n_r, 6)}/{n(it.Q)} = {n(fill, 6)}",
    })
    return steps


def _beta_steps(inp: Inputs, it: Iteration) -> list:
    dist = inp.dist
    target = (1.0 - inp.beta) * it.Q
    steps = [_eoq(inp, it), {
        "label": "Fill rate: the expected shortage per cycle may be (1 − β)·Q",
        "tex": (rf"n(r)=(1-\beta)\,Q=(1-{g(inp.beta)})({n(it.Q)})={n(target, 6)}"),
        "plain": f"n(r) = (1 - beta)·Q = (1 - {g(inp.beta)})({n(it.Q)}) = {n(target, 6)}",
    }]
    steps += loss_root_steps(dist, target, it.r, "r")
    steps.append({
        "label": "The chance a cycle runs out, for information",
        "tex": rf"1-G(r)={n(it.tail, 6)}",
        "plain": f"1 - G(r) = {n(it.tail, 6)}",
    })
    return steps


def loss_root_steps(dist, target: float, level: float, sym: str) -> list:
    """Solve n(level) = target for the level, per distribution.

    Shared by the Policy 1 fill rate (``sym`` = r, target (1 − β)·Q) and Policy 2
    (``sym`` = S, target (1 − β)·D·T).
    """
    out = []
    low = dist.support_low
    if math.isfinite(low) and level == low and target >= dist.loss(low):
        out.append({
            "label": "Already met at the lowest level demand can take",
            "tex": rf"n({g(low)})={n(dist.loss(low), 6)}\le{n(target, 6)}\ \Rightarrow\ {sym}={g(low)}",
            "plain": f"n({g(low)}) = {n(dist.loss(low), 6)} <= {n(target, 6)}, so {sym} = {g(low)}",
        })
    elif dist.name == "Normal":
        k = (level - dist.mu) / dist.sigma
        out += [
            {"label": "In unit-normal terms: the loss function at the safety factor",
             "tex": (rf"G_u(k)=\dfrac{{n({sym})}}{{\sigma}}=\dfrac{{{n(target, 6)}}}"
                     rf"{{{g(dist.sigma)}}}={n(target / dist.sigma, 6)}"),
             "plain": (f"Gu(k) = n({sym})/sigma = {n(target, 6)}/{g(dist.sigma)}"
                       f" = {n(target / dist.sigma, 6)}")},
            {"label": "Read k off Table B.1 (solved numerically here)",
             "tex": rf"k={n(k, 5)}",
             "plain": f"k = {n(k, 5)}"},
            {"label": f"The level {sym}",
             "tex": (rf"{sym}=\mu+k\,\sigma={g(dist.mu)}+({n(k, 5)})({g(dist.sigma)})"
                     rf"={n(level)}"),
             "plain": (f"{sym} = mu + k·sigma = {g(dist.mu)} + ({n(k, 5)})"
                       f"({g(dist.sigma)}) = {n(level)}")},
        ]
    elif dist.name == "Uniform":
        out.append({
            "label": f"Solve the uniform loss function for {sym}",
            "tex": (rf"\dfrac{{(b-{sym})^2}}{{2(b-a)}}=n({sym})\ \Rightarrow\ "
                    rf"{sym}=b-\sqrt{{2(b-a)\,n({sym})}}={g(dist.b)}-\sqrt{{2({g(dist.b)}-"
                    rf"{g(dist.a)})({n(target, 6)})}}={n(level)}"),
            "plain": (f"(b - {sym})^2/(2(b - a)) = n({sym}), so {sym} = b - sqrt(2(b - a)·n({sym}))"
                      f" = {g(dist.b)} - sqrt(2({g(dist.b)} - {g(dist.a)})"
                      f"({n(target, 6)})) = {n(level)}"),
        })
    elif dist.name == "Exponential":
        out.append({
            "label": f"Solve the exponential loss function for {sym}",
            "tex": (rf"\dfrac{{e^{{-\lambda {sym}}}}}{{\lambda}}=n({sym})\ \Rightarrow\ "
                    rf"{sym}=-\dfrac{{\ln(\lambda\,n({sym}))}}{{\lambda}}"
                    rf"=-\dfrac{{\ln(({g(dist.lam)})({n(target, 6)}))}}{{{g(dist.lam)}}}"
                    rf"={n(level)}"),
            "plain": (f"e^(-lambda·{sym})/lambda = n({sym}), so {sym} = -ln(lambda·n({sym}))/lambda"
                      f" = -ln(({g(dist.lam)})({n(target, 6)}))/{g(dist.lam)}"
                      f" = {n(level)}"),
        })
    else:
        out.append({
            "label": "The smallest whole number whose shortage fits",
            "tex": (rf"{sym}=\min\{{\,k\in\mathbb{{Z}}: n(k)\le {n(target, 6)}\,\}}"
                    rf"={n(level, 0)}"),
            "plain": (f"{sym} = smallest integer k with n(k) <= {n(target, 6)}"
                      f" = {n(level, 0)}"),
        })
    return out


# --------------------------------------------------------------------------- #
#  Policy 2 — periodic review (R, S)
# --------------------------------------------------------------------------- #

def _scaled_steps(res) -> list:
    """How demand over T + L comes from lead-time demand."""
    lead = res.inputs.dist
    prot = res.protection
    f = res.factor
    if f != f:          # NaN: the protection-interval demand was given directly
        return [{
            "label": "Demand over the protection interval T + L, as given",
            "tex": rf"X_{{T+L}}\sim\text{{{prot.describe()}}}",
            "plain": f"X(T+L) ~ {prot.describe()}",
        }]
    if prot.name == "Normal":
        tex = (rf"\mu_{{T+L}}=\mu f=({g(lead.mu)})({n(f, 6)})={n(prot.mu, 6)},\quad "
               rf"\sigma_{{T+L}}=\sigma\sqrt{{f}}=({g(lead.sigma)})\sqrt{{{n(f, 6)}}}"
               rf"={n(prot.sigma, 6)}")
        plain = (f"mu(T+L) = mu·f = ({g(lead.mu)})({n(f, 6)}) = {n(prot.mu, 6)},  "
                 f"sigma(T+L) = sigma·sqrt(f) = ({g(lead.sigma)})sqrt({n(f, 6)})"
                 f" = {n(prot.sigma, 6)}")
        label = "Scale the normal: the mean by f, the deviation by √f"
    elif prot.name == "Uniform":
        tex = (rf"a_{{T+L}}=a f=({g(lead.a)})({n(f, 6)})={n(prot.a, 6)},\quad "
               rf"b_{{T+L}}=b f=({g(lead.b)})({n(f, 6)})={n(prot.b, 6)}")
        plain = (f"a(T+L) = a·f = ({g(lead.a)})({n(f, 6)}) = {n(prot.a, 6)},  "
                 f"b(T+L) = b·f = ({g(lead.b)})({n(f, 6)}) = {n(prot.b, 6)}")
        label = ("Scale both bounds by f — the lecture's simplification (slide 25); "
                 "a sum of uniforms is not exactly uniform")
    elif prot.name == "Exponential":
        tex = (rf"\text{{mean}}_{{T+L}}=({g(lead.mean)})({n(f, 6)})={n(prot.mean, 6)},"
               rf"\quad\lambda_{{T+L}}={n(prot.lam, 6)}")
        plain = (f"mean(T+L) = ({g(lead.mean)})({n(f, 6)}) = {n(prot.mean, 6)},  "
                 f"lambda(T+L) = {n(prot.lam, 6)}")
        label = ("Scale the mean by f — the lecture's simplification; a sum of "
                 "exponentials is Erlang")
    else:
        tex = rf"\lambda_{{T+L}}=\lambda f=({g(lead.lam)})({n(f, 6)})={n(prot.lam, 6)}"
        plain = f"lambda(T+L) = lambda·f = ({g(lead.lam)})({n(f, 6)}) = {n(prot.lam, 6)}"
        label = "Scale the Poisson mean by f (exact: Poisson counts add)"
    T, L = res.T, res.inputs.lead_time
    return [
        {"label": "The protection interval: one review period plus the lead time",
         "tex": rf"f=\dfrac{{T+L}}{{L}}=\dfrac{{{g(T)}+{g(L)}}}{{{g(L)}}}={n(f, 6)}",
         "plain": f"f = (T + L)/L = ({g(T)} + {g(L)})/{g(L)} = {n(f, 6)}"},
        {"label": label, "tex": tex, "plain": plain},
    ]


def periodic_steps(res) -> list:
    """Policy 2 written out: protection interval, the condition, S, the cost.

    ``res`` is a :class:`rq_solver.PeriodicResult`; every number shown is one
    it recorded.
    """
    inp = res.inputs
    dist = res.protection
    mode = inp.stockout
    steps = _scaled_steps(res)
    S = res.S
    if mode == "B2":
        tail = inp.h * res.T / inp.p
        steps.append({
            "label": "Slide 49: the share of demand over T + L that may exceed S",
            "tex": (rf"1-G(S)=\dfrac{{h\,T}}{{p}}=\dfrac{{({g(inp.h)})({g(res.T)})}}"
                    rf"{{{g(inp.p)}}}={n(tail, 6)}\ \Rightarrow\ G(S)={n(res.target, 6)}"),
            "plain": (f"1 - G(S) = h·T/p = ({g(inp.h)})({g(res.T)})/{g(inp.p)}"
                      f" = {n(tail, 6)}, so G(S) = {n(res.target, 6)}"),
        })
        if not res.degenerate:
            steps += _quantile_steps(dist, res.target, S)
    elif mode == "alpha":
        steps.append({
            "label": "Cycle service level: the cdf at S is α",
            "tex": rf"G(S)=\alpha={g(inp.alpha)}",
            "plain": f"G(S) = alpha = {g(inp.alpha)}",
        })
        steps += _quantile_steps(dist, res.target, S)
    elif mode == "B1":
        steps.append({
            "label": "The density of demand over T + L at S",
            "tex": (rf"g(S)=\dfrac{{h\,T}}{{B_1}}=\dfrac{{({g(inp.h)})({g(res.T)})}}"
                    rf"{{{g(inp.B1)}}}={n(res.target, 6)}"),
            "plain": (f"g(S) = h·T/B1 = ({g(inp.h)})({g(res.T)})/{g(inp.B1)}"
                      f" = {n(res.target, 6)}"),
        })
        steps += density_root_steps(dist, res.target, S, "S", r"\tfrac{hT}{B_1}",
                                    "h·T/B1")
    else:
        steps.append({
            "label": "Fill rate: expected shortage per review may be (1 − β)·D·T",
            "tex": (rf"n(S)=(1-\beta)\,D\,T=(1-{g(inp.beta)})({g(inp.D)})({g(res.T)})"
                    rf"={n(res.target, 6)}"),
            "plain": (f"n(S) = (1 - beta)·D·T = (1 - {g(inp.beta)})({g(inp.D)})"
                      f"({g(res.T)}) = {n(res.target, 6)}"),
        })
        steps += loss_root_steps(dist, res.target, S, "S")
    D, L, T = inp.D, inp.lead_time, res.T
    steps += [
        {"label": "Safety stock: S less expected demand over T + L",
         "tex": (rf"SS=S-D(T+L)={n(S)}-({g(D)})({g(T + L)})={n(res.safety_stock)}"),
         "plain": f"SS = S - D(T + L) = {n(S)} - ({g(D)})({g(T + L)}) = {n(res.safety_stock)}"},
        {"label": "Average inventory (slide 48)",
         "tex": (rf"S-DL-\dfrac{{DT}}{{2}}={n(S)}-({g(D)})({g(L)})-"
                 rf"\dfrac{{({g(D)})({g(T)})}}{{2}}={n(res.average_inventory)}"),
         "plain": (f"S - D·L - D·T/2 = {n(S)} - ({g(D)})({g(L)}) - ({g(D)})({g(T)})/2"
                   f" = {n(res.average_inventory)}")},
        {"label": "Cost per unit time, without the purchase cost D·v",
         "tex": (rf"Y_2=\dfrac{{A}}{{T}}+h\left(S-DL-\dfrac{{DT}}{{2}}\right)"
                 + (r"+\dfrac{p\,n(S)}{T}" if mode == "B2" else
                    r"+\dfrac{B_1(1-G(S))}{T}" if mode == "B1" else "")
                 + rf"={n(res.ordering_cost)}+{n(res.holding_cost)}"
                 + (f"+{n(res.shortage_cost)}" if mode in ("B1", "B2") else "")
                 + rf"={n(res.cost_excluding_purchase)}"),
         "plain": (f"Y2 = A/T + h(S - D·L - D·T/2)"
                   + (" + p·n(S)/T" if mode == "B2" else
                      " + B1·(1 - G(S))/T" if mode == "B1" else "")
                   + f" = {n(res.ordering_cost)} + {n(res.holding_cost)}"
                   + (f" + {n(res.shortage_cost)}" if mode in ("B1", "B2") else "")
                   + f" = {n(res.cost_excluding_purchase)}")},
    ]
    return steps


def _quantile_steps(dist, target: float, S: float) -> list:
    """S as the ``target`` quantile of demand over T + L."""
    if dist.name == "Normal":
        z = (S - dist.mu) / dist.sigma
        return [
            {"label": "Read z off the standard normal",
             "tex": rf"z=\Phi^{{-1}}({n(target, 6)})={n(z, 5)}",
             "plain": f"z = inverse normal of {n(target, 6)} = {n(z, 5)}"},
            {"label": "Order-up-to level",
             "tex": (rf"S=\mu_{{T+L}}+z\,\sigma_{{T+L}}={g(dist.mu)}+({n(z, 5)})"
                     rf"({g(dist.sigma)})={n(S)}"),
             "plain": (f"S = mu + z·sigma = {g(dist.mu)} + ({n(z, 5)})"
                       f"({g(dist.sigma)}) = {n(S)}")},
        ]
    if dist.name == "Uniform":
        return [{"label": "Order-up-to level, from the uniform quantile",
                 "tex": (rf"S=a+G(S)(b-a)={g(dist.a)}+({n(target, 6)})"
                         rf"({g(dist.b)}-{g(dist.a)})={n(S)}"),
                 "plain": (f"S = a + G(S)(b - a) = {g(dist.a)} + ({n(target, 6)})"
                           f"({g(dist.b)} - {g(dist.a)}) = {n(S)}")}]
    if dist.name == "Exponential":
        return [{"label": "Order-up-to level, from the exponential quantile",
                 "tex": (rf"S=-\dfrac{{\ln(1-G(S))}}{{\lambda}}"
                         rf"=-\dfrac{{\ln({n(1.0 - target, 6)})}}{{{g(dist.lam)}}}"
                         rf"={n(S)}"),
                 "plain": (f"S = -ln(1 - G(S))/lambda = -ln({n(1.0 - target, 6)})"
                           f"/{g(dist.lam)} = {n(S)}")}]
    return [{"label": "Order-up-to level: the smallest whole number reaching that cdf",
             "tex": (rf"S=\min\{{\,k\in\mathbb{{Z}}: G(k)\ge {n(target, 6)}\,\}}"
                     rf"={n(S, 0)}"),
             "plain": (f"S = smallest integer k with G(k) >= {n(target, 6)}"
                       f" = {n(S, 0)}")}]
