"""Presentation layer shared by the desktop and the web front end.

Both apps render exactly the same numbers because both call these functions.
Nothing here imports tkinter or streamlit.
"""

from __future__ import annotations

import csv
import io
import math

from rq_solver import STOCKOUT_MODES, Comparison, PeriodicResult, Result

#: Iteration t is counted from 0 and runs Q_t → r_t → n(r_t) → Q_t+1, so
#: the row for t = 0 starts at the EOQ.
ITERATION_HEADERS = [
    "Iter t", "Q_t (in)", "1 − G(r_t) = Q_t·h/pD", "G(r_t)", "r_t", "n(r_t)",
    "Q_t+1 (out)", "|r_t − r_t−1|",
]

#: The same columns under the other stockout bases. B1 reads r off the density
#: condition (2'), so 1 − G(r_t) and G(r_t) are results there, not targets; a
#: service level leaves Q at the EOQ and has a single row.
ITERATION_HEADERS_BY_MODE = {
    "B2": ITERATION_HEADERS,
    "B1": ["Iter t", "Q_t (in)", "1 − G(r_t)", "G(r_t)",
           "r_t: g(r_t) = Q_t·h/(B1·D)", "n(r_t)", "Q_t+1 (out)", "|r_t − r_t−1|"],
    "alpha": ["Iter t", "Q = EOQ", "1 − G(r) = 1 − α", "G(r) = α", "r", "n(r)",
              "Q (unchanged)", "|Δr|"],
    "beta": ["Iter t", "Q = EOQ", "1 − G(r)", "G(r)", "r: n(r) = (1 − β)·Q",
             "n(r)", "Q (unchanged)", "|Δr|"],
}


def iteration_headers(res: Result) -> list:
    """The iteration table's column heads for this result's stockout basis."""
    return ITERATION_HEADERS_BY_MODE[res.inputs.stockout]


def iterations_used(res: Result) -> str:
    """How many iterations ran, and which numbers they had: '3 (t = 0 … 2)'."""
    count = len(res.iterations)
    if count == 1:
        return "1 (t = 0)"
    return f"{count} (t = 0 … {res.iterations[-1].index})"


def answer_source(res: Result) -> str:
    """Which iterate the answer is, in the notation the iteration is shown in.

    The answer is read at the end of the last iteration T: r* is r_T from
    equation (2) and Q* is the Q_{T+1} equation (1) returned. The single-pass
    approximation keeps Q at the EOQ instead, so there Q* = Q_0.
    """
    if not res.iterations:
        return ""
    last = res.iterations[-1].index
    if res.inputs.stockout in ("alpha", "beta"):
        return "Q* = Q0 (the EOQ), r* from the service level"
    if res.single_pass:
        return "Q* = Q0 (the EOQ), r* = r0 from iteration 0"
    return (f"Q* = Q{last + 1}, r* = r{last}: "
            f"both from iteration {last}, the last one")


def fmt(value: float, dp: int = 3) -> str:
    """Format a number for display, keeping blanks for undefined entries."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return "—"
    if isinstance(value, float) and math.isinf(value):
        return "∞" if value > 0 else "−∞"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.3f}"


def summary_rows(res: Result) -> list:
    """One dict per line of the answer.

    ``name`` is the quantity in words, ``formula`` is it in plain notation and
    ``tex`` the same for a typesetter. The plain-text consumers — the desktop
    window, the CSV, the saved report — join name and formula; the web page
    renders the TeX instead.
    """
    inp = res.inputs
    rows = [
        ("Q", "Order quantity", "Q*", r"Q^{*}",
         fmt(res.Q, 4), "units per replenishment"),
        ("r", "Reorder point", "r*", r"r^{*}",
         fmt(res.r, 4), "units of inventory position at the reorder point"),
        ("ss", "Safety stock", "SS = r* − D·l", r"SS=r^{*}-D\,l",
         fmt(res.safety_stock, 4), "units"),
        ("n", "Expected shortage per cycle", "n(r*)", r"n(r^{*})",
         fmt(res.n_r, 6), "units"),
        ("theta", "Expected lead-time demand", "θ = D·l", r"\theta=D\,l",
         fmt(inp.theta, 4), "units"),
        ("eoq", "EOQ, where the iteration starts", "Q0 = √(2AD/h)",
         r"Q_0=\sqrt{\tfrac{2AD}{h}}", fmt(inp.eoq, 4), "units"),
        ("fill", "Fill rate", "1 − n(r*)/Q*", r"1-\tfrac{n(r^{*})}{Q^{*}}",
         f"{res.fill_rate * 100:,.3f} %", "fraction of demand served from stock"),
        ("orders", "Replenishments per period", "D/Q*", r"\tfrac{D}{Q^{*}}",
         fmt(res.orders_per_period, 4), "orders"),
        ("cycle", "Cycle length", "Q*/D", r"\tfrac{Q^{*}}{D}",
         fmt(res.cycle_length, 6), "time units"),
        ("passes", "Iterations used", "", "", iterations_used(res),
         answer_source(res)),
        ("converged", "Converged", "", "",
         "yes" if res.converged else "no", ""),
    ]
    mode = inp.stockout
    if mode != "B2":
        # Placed after the fill rate, so a B2 report keeps its rows exactly.
        at = [row[0] for row in rows].index("fill") + 1
        rows[at:at] = [
            ("basis", "Stockout basis", STOCKOUT_MODES[mode]["symbol"],
             STOCKOUT_MODES[mode]["tex"],
             STOCKOUT_MODES[mode]["label"], f"{fmt(inp.stockout_value, 6)}"),
            ("csl", "Cycle service level", "G(r*)", r"G(r^{*})",
             f"{res.cycle_service_level * 100:,.3f} %",
             "chance a cycle does not run out"),
        ]
    return [{"key": key, "name": name, "formula": formula, "tex": tex,
             "label": f"{name}  {formula}".rstrip(), "value": value, "unit": unit}
            for key, name, formula, tex, value, unit in rows]


def iteration_rows(res: Result) -> list:
    out = []
    for it in res.iterations:
        out.append([
            fmt(it.index), fmt(it.Q, 4), fmt(it.tail, 6), fmt(it.G_target, 6),
            fmt(it.r, 4), fmt(it.n_r, 6), fmt(it.Q_next, 4), fmt(it.delta_r, 6),
        ])
    return out


#: The B1 shortage line, which replaces the B2 one under that basis.
COST_TEX_B1 = r"B_1\tfrac{D}{Q}\,(1-G(r))"

COST_TEX = {
    "holding":  r"h\,(\tfrac{Q}{2}+r-D\,l)",
    "ordering": r"\tfrac{AD}{Q}",
    "shortage": r"\tfrac{p\,D\,n(r)}{Q}",
    "purchase": r"D\,v",
    "total":    r"Y(Q,r)",
}


def cost_rows(res: Result) -> list:
    """One dict per line of the cost, shaped like :func:`summary_rows`."""
    b1 = res.inputs.stockout == "B1"
    return [{"key": key, "name": name, "formula": formula,
             "tex": COST_TEX_B1 if (b1 and key == "shortage") else COST_TEX.get(key, ""),
             "label": f"{name}  {formula}".rstrip(), "value": fmt(value, 4)}
            for key, name, formula, value in res.cost_breakdown()]


def input_rows(res: Result, units: dict | None = None) -> list:
    return input_rows_for(res.inputs, units)


def input_rows_for(inp, units: dict | None = None) -> list:
    """The data as the model sees it, from ``Inputs`` alone.

    Split out from :func:`input_rows` so the terminal walkthrough can print it
    *before* solving — at the point in the working where it is established,
    rather than after the answer already exists.
    """
    base = f" per {units['base_label']}" if units else ""
    lead = (f"{fmt(units['lead_entered'], 4)} {units['lead_label']}s "
            f"= {fmt(inp.lead_time, 6)} {units['base_label']}s"
            if units else fmt(inp.lead_time, 6))
    rows = [
        ("Demand rate  D", fmt(inp.D, 4) + base),
        ("Ordering cost  A", fmt(inp.A, 4)),
        ("Holding cost  h", fmt(inp.h, 6) + base),
        _stockout_input(inp),
        ("Lead time  l", lead),
        ("Lead-time demand", inp.dist.describe()),
    ]
    if inp.v > 0:
        rows.append(("Unit cost  v", fmt(inp.v, 4)))
    return rows


def _stockout_input(inp) -> tuple:
    """The input row for whatever the stockout basis reads."""
    mode = getattr(inp, "stockout", "B2")
    if mode == "B1":
        return ("Cost per stockout occasion  B1", fmt(inp.B1, 4))
    if mode == "alpha":
        return ("Cycle service level  α", fmt(inp.alpha, 6))
    if mode == "beta":
        return ("Fill rate  β", fmt(inp.beta, 6))
    return ("Penalty cost  p", fmt(inp.p, 4))


# --------------------------------------------------------------------------- #
#  Policy 2 and the comparison
# --------------------------------------------------------------------------- #

PERIODIC_COST_TEX = {
    "holding":  r"h\,(S-D\,L-\tfrac{D\,T}{2})",
    "ordering": r"\tfrac{A}{T}",
    "shortage": r"\tfrac{p\,n(S)}{T}",
    "purchase": r"D\,v",
    "total":    r"Y_2(S)",
}
PERIODIC_COST_TEX_B1 = r"\tfrac{B_1(1-G(S))}{T}"


def _rows(rows: list) -> list:
    return [{"key": key, "name": name, "formula": formula, "tex": tex,
             "label": f"{name}  {formula}".rstrip(), "value": value, "unit": unit}
            for key, name, formula, tex, value, unit in rows]


def periodic_summary_rows(res: PeriodicResult, units: dict | None = None) -> list:
    """Policy 2's answer, shaped like :func:`summary_rows`."""
    base = units["base_label"] if units else "time unit"
    rows = [
        ("S", "Order-up-to level", "S*", r"S^{*}", fmt(res.S, 4),
         "units, ordered up to at every review"),
        ("T", "Review period", "T", r"T", fmt(res.T, 6), f"{base}s"),
        ("protection", "Demand over T + L", "X(T+L)", r"X_{T+L}",
         res.protection.describe(), ""),
        ("ss", "Safety stock", "SS = S* − D·(T + L)", r"SS=S^{*}-D\,(T+L)",
         fmt(res.safety_stock, 4), "units"),
        ("avg", "Average inventory", "S* − D·L − D·T/2",
         r"S^{*}-D\,L-\tfrac{D\,T}{2}", fmt(res.average_inventory, 4), "units"),
        ("n", "Expected shortage per review", "n(S*)", r"n(S^{*})",
         fmt(res.n_S, 6), "units"),
        ("csl", "Cycle service level", "G(S*)", r"G(S^{*})",
         f"{res.G_S * 100:,.3f} %", "chance a review cycle does not run out"),
        ("fill", "Fill rate", "1 − n(S*)/(D·T)", r"1-\tfrac{n(S^{*})}{D\,T}",
         f"{res.fill_rate * 100:,.3f} %", "fraction of demand served from stock"),
        ("orders", "Reviews per period", "1/T", r"\tfrac{1}{T}",
         fmt(res.orders_per_period, 6), "orders"),
    ]
    return _rows(rows)


def periodic_cost_rows(res: PeriodicResult) -> list:
    """Policy 2's cost lines, shaped like :func:`cost_rows`."""
    b1 = res.mode == "B1"
    return [{"key": key, "name": name, "formula": formula,
             "tex": (PERIODIC_COST_TEX_B1 if (b1 and key == "shortage")
                     else PERIODIC_COST_TEX.get(key, "")),
             "label": f"{name}  {formula}".rstrip(), "value": fmt(value, 4)}
            for key, name, formula, value in res.cost_breakdown()]


def comparison_rows(cmp: Comparison, units: dict | None = None) -> list:
    """Policy 1 against Policy 2, cost per base time unit (named when known)."""
    per = f"per {units['base_label']}" if units else "per time unit"
    rows = [
        ("policy1", "Policy 1, continuous review (r, Q)", "Y1 − D·v",
         r"Y_1-D\,v", fmt(cmp.policy1, 4), per),
        ("policy2", "Policy 2, periodic review (R, S)", "Y2 − D·v",
         r"Y_2-D\,v", fmt(cmp.policy2, 4), per),
    ]
    if cmp.purchase > 0.0:
        rows.append(("purchase", "Purchase cost, the same for both", "D·v",
                     r"D\,v", fmt(cmp.purchase, 4), "does not affect the choice"))
    rows += [
        ("difference", "Difference", "|Y1 − Y2|", r"\lvert Y_1-Y_2\rvert",
         fmt(cmp.difference, 4), per),
        ("chosen", "Cheaper policy", "", "", cmp.chosen, ""),
    ]
    return _rows(rows)


def headline(res: Result) -> str:
    return (f"Q* = {res.Q:,.3f}    r* = {res.r:,.3f}    "
            f"safety stock = {res.safety_stock:,.3f}")


def to_csv(res: Result, units: dict | None = None,
           policy2: PeriodicResult | None = None,
           comparison: Comparison | None = None) -> str:
    """The whole report as CSV text, ready to save or download.

    With ``policy2`` (and ``comparison``) the periodic-review answer and the
    choice between the two follow the Policy 1 report; without them the text
    is exactly what it always was.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")

    w.writerow(["(r, Q) model — iterative solution"])
    w.writerow([])
    w.writerow(["Inputs"])
    for label, value in input_rows(res, units):
        w.writerow([label, value])

    w.writerow([])
    w.writerow(["Answer"])
    for row in summary_rows(res):
        w.writerow([row["label"], row["value"], row["unit"]])

    w.writerow([])
    w.writerow(["Iterations"])
    w.writerow(iteration_headers(res))
    for row in iteration_rows(res):
        w.writerow(row)

    w.writerow([])
    w.writerow(["Cost at the solution"])
    for row in cost_rows(res):
        w.writerow([row["label"], row["value"]])

    if res.notes:
        w.writerow([])
        w.writerow(["Notes"])
        for note in res.notes:
            w.writerow([note])

    if policy2 is not None:
        w.writerow([])
        w.writerow(["Policy 2 — periodic review (R, S)"])
        for row in periodic_summary_rows(policy2, units):
            w.writerow([row["label"], row["value"], row["unit"]])
        w.writerow([])
        w.writerow(["Policy 2 cost"])
        for row in periodic_cost_rows(policy2):
            w.writerow([row["label"], row["value"]])
        if policy2.notes:
            w.writerow([])
            w.writerow(["Policy 2 notes"])
            for note in policy2.notes:
                w.writerow([note])
    if comparison is not None:
        w.writerow([])
        w.writerow(["Policy 1 against Policy 2"])
        for row in comparison_rows(comparison, units):
            w.writerow([row["label"], row["value"], row["unit"]])
        for note in comparison.notes:
            w.writerow([note])

    return buf.getvalue()


def to_text(res: Result, units: dict | None = None,
            policy2: PeriodicResult | None = None,
            comparison: Comparison | None = None) -> str:
    """A plain-text report, handy for pasting next to a manual solution."""
    lines = ["(r, Q) MODEL — ITERATIVE SOLUTION", "=" * 72, "", "INPUTS"]
    for label, value in input_rows(res, units):
        lines.append(f"  {label:<40}{value}")
    lines += ["", "ANSWER"]
    for row in summary_rows(res):
        lines.append(f"  {row['label']:<40}{row['value']:>18}  {row['unit']}")
    lines += ["", "ITERATIONS"]
    widths = [8, 12, 24, 12, 12, 12, 14, 14]
    lines.append("  " + "".join(h.ljust(w) for h, w in zip(iteration_headers(res), widths)))
    for row in iteration_rows(res):
        lines.append("  " + "".join(c.ljust(w) for c, w in zip(row, widths)))
    lines += ["", "COST AT THE SOLUTION"]
    for row in cost_rows(res):
        lines.append(f"  {row['label']:<40}{row['value']:>18}")
    if res.notes:
        lines += ["", "NOTES"]
        for note in res.notes:
            lines.append(f"  - {note}")
    if policy2 is not None:
        lines += ["", "POLICY 2 — PERIODIC REVIEW (R, S)"]
        for row in periodic_summary_rows(policy2, units):
            lines.append(f"  {row['label']:<40}{row['value']:>18}  {row['unit']}")
        lines += ["", "POLICY 2 COST"]
        for row in periodic_cost_rows(policy2):
            lines.append(f"  {row['label']:<40}{row['value']:>18}")
        for note in policy2.notes:
            lines.append(f"  - {note}")
    if comparison is not None:
        lines += ["", "POLICY 1 AGAINST POLICY 2"]
        for row in comparison_rows(comparison, units):
            lines.append(f"  {row['label']:<40}{row['value']:>18}  {row['unit']}")
        for note in comparison.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)
