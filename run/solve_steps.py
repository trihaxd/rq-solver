"""The (s, Q) iteration walked through one step at a time, in the terminal.

    python solve_steps.py                    pick a problem from the menu
    python solve_steps.py --problem hw1      straight into Homework 2, Problem 1
    python solve_steps.py --problem hw3      the six cases of Problem 3, as a menu
    python solve_steps.py -p hw3-mask-1      Problem 3, blue masks, Scenario 1
    python solve_steps.py --problem new      type a fresh problem in
    python solve_steps.py --no-pause         run it through without stopping
    python solve_steps.py --max-iter 3       stop after three iterations (0, 1, 2)

Problem 3 keys are ``hw3-<product>-<scenario>``: product ``mask``,
``sanitizer`` or ``gown``; scenario ``1`` (98 % cycle service level, α) or
``2`` (backorder cost p = 30 % of v).

Press Enter to advance, ``s`` inside the iteration to skip to the answer (the
iterations left are shown as one table), ``a`` to run the rest without
stopping, ``q`` to leave. In a console one key is enough; from a pipe, follow
it with Enter. Every line prints the formula,
the numbers put into it and the result, so the working can be read off the
screen and checked against a manual solution.

The walkthrough follows the problem's stockout basis — p per unit short (B2),
B1 per stockout occasion, a cycle service level α or a fill rate β — and, when
the problem gives a review period T, goes on to Policy 2 (order up to S every
T) and names the cheaper of the two policies.

Standard library only, like the rest of the app, and it drives the same
``rq_solver``/``derive``/``steps``/``report`` code the page does — so the
terminal and the window cannot disagree about an answer.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import report
from derive import PERIOD_DISTRIBUTIONS, derive
from rq_solver import (
    DISTRIBUTIONS, EXAMPLES, STOCKOUT_MODES, Inputs, SolverError,
    build_distribution, compare_policies, solve_periodic, solve_rq,
)
from steps import pass_steps, periodic_steps
from timeunits import UNITS, convert, unit_label, unit_plural


def _problem_3_key(product: str, scenario: int) -> str:
    """The EXAMPLES key for one Problem 3 case, found rather than retyped, so
    a reworded label in the solver cannot leave a dead shortcut here."""
    found = [k for k in EXAMPLES
             if k.startswith(f"Homework 2, Problem 3 — {product},")
             and f"Scenario {scenario}" in k]
    if len(found) != 1:
        raise RuntimeError(f"Problem 3, {product}, Scenario {scenario}: expected "
                           f"one built-in entry, found {len(found)}")
    return found[0]


#: Problem 3's shortcuts, in the order the sub-menu lists them.
PROBLEM_3 = {
    f"hw3-{short}-{scenario}": _problem_3_key(product, scenario)
    for short, product in (("mask", "blue masks"),
                           ("sanitizer", "sanitizer dispensers"),
                           ("gown", "sterile gowns"))
    for scenario in (1, 2)
}

#: Short names for the built-in problems, so a flag can name one. Only the
#: homework problems are offered; the lecture-deck cases are test-only.
#: ``hw3`` on its own is not a problem but the sub-menu of the six below.
ALIASES = {
    "hw1": "Homework 2, Problem 1 — IEM, monthly N(28, 8²)",
    "hw2": "Homework 2, Problem 2 — computers, weekly N(100, 3²)",
    **PROBLEM_3,
}

#: What the top menu calls the Problem 3 group.
PROBLEM_3_LABEL = ("Homework 2, Problem 3 — eye clinic: masks, sanitizer, "
                   "gowns (6 cases)")

WIDTH = 78


# --------------------------------------------------------------------------- #
#  Printing
# --------------------------------------------------------------------------- #

#: The glyphs the working is written with, and their ASCII stand-ins. A Windows
#: console left on code page 1252 — or any redirect to a pipe under a non-UTF-8
#: locale — cannot encode these, and the walkthrough has to stay readable there
#: rather than stopping on a UnicodeEncodeError halfway down a derivation.
ASCII_FALLBACK = {
    "─": "-", "━": "=", "·": "*", "×": "x", "−": "-", "—": "--", "←": "<-",
    "≥": ">=", "≤": "<=", "Δ": "delta ", "θ": "theta", "σ": "sigma",
    "μ": "mu", "λ": "lambda", "√": "sqrt", "∞": "inf", "²": "^2", "⁻": "^-",
    "Φ": "Phi", "φ": "phi", "≈": "~=", "ö": "o", "ë": "e",
    # The stockout bases and Policy 2 bring their own symbols.
    "α": "alpha", "β": "beta", "₁": "1", "₂": "2", "₀": "0", "¹": "1",
    "³": "^3", "→": "->", "…": "...", "–": "-", "π": "pi", "•": "*",
    "≠": "!=", "∈": " in ", "ℤ": "Z", "⌊": "floor(", "⌋": ")",
    "’": "'", "‘": "'", "“": '"', "”": '"',
}


def _prepare(stream):
    """Make the stream take UTF-8 if it will, and say whether it managed.

    Redirecting to a pipe picks up the locale encoding, which on a Vietnamese
    or Western Windows is cp1252; reconfiguring fixes that outright. Where it
    cannot be reconfigured, the caller falls back to ASCII.
    """
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
        return True
    except (AttributeError, ValueError, OSError):
        pass
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "".join(ASCII_FALLBACK).encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class Console:
    """Colour when the terminal takes it, plain text when it does not."""

    def __init__(self, colour: bool, pause: bool, unicode_ok: bool = True):
        self.colour = colour
        self.pause = pause
        self.unicode_ok = unicode_ok
        self.stopped = False
        self.skipping = False

    def t(self, text: str) -> str:
        """Text as this terminal can print it."""
        if self.unicode_ok:
            return text
        for rich, plain in ASCII_FALLBACK.items():
            text = text.replace(rich, plain)
        return text.encode("ascii", "replace").decode("ascii")

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def bold(self, text): return self._c("1", self.t(text))
    def dim(self, text): return self._c("2", self.t(text))
    def cyan(self, text): return self._c("36", self.t(text))
    def green(self, text): return self._c("32", self.t(text))
    def yellow(self, text): return self._c("33", self.t(text))
    def red(self, text): return self._c("31", self.t(text))

    def say(self, text: str = ""):
        """Every plain line goes through here, so none can carry a glyph the
        terminal cannot encode."""
        print(self.t(text))

    def rule(self, char="─"):
        print(self.dim(char * WIDTH))

    def title(self, text: str):
        self.say()
        self.rule("━")
        self.say("  " + self.bold(text))
        self.rule("━")

    def heading(self, text: str):
        print()
        print("  " + self.bold(self.cyan(text)))
        self.rule()

    def step(self, number, label: str, body: str):
        """One worked line: what is being done, then the arithmetic."""
        tag = self.green(f"  [{number}] ")
        print(f"{tag}{self.bold(label)}")
        for line in _wrap(self.t(body), WIDTH - 8):
            print("        " + line)

    def para(self, text: str, paint=None):
        """A sentence too long for one line, wrapped at the page width."""
        for line in _wrap(self.t(text), WIDTH - 6):
            print("    " + (paint(line) if paint else line))

    def note(self, text: str):
        for line in _wrap(self.t(text), WIDTH - 8):
            print("    " + self.yellow(line))

    def kv(self, label: str, value: str, unit: str = ""):
        pad = self.t(label).ljust(44)
        tail = f"  {self.dim(unit)}" if unit else ""
        print(f"    {pad}{self.bold(self.t(value).rjust(16))}{tail}")

    def wait(self, prompt: str = "Enter to continue", skippable: bool = False):
        """Hold until the reader is ready. ``q`` leaves the walkthrough, ``a``
        runs the rest without stopping, and — inside the iteration, where
        ``skippable`` is set — ``s`` skips what is left of it."""
        if self.stopped or not self.pause:
            return
        if skippable:
            prompt = "Enter = next step · s = skip to the answer"
        try:
            answer = self._ask(prompt).strip().lower()
        except EOFError:
            self.stopped = True
            self.pause = False
            return
        except KeyboardInterrupt:
            print()
            raise SystemExit(130)
        if answer in {"q", "quit", "exit"}:
            print(self.dim("    (stopping here)"))
            raise SystemExit(0)
        if answer in {"a", "all"}:
            print(self.dim("    (running the rest without stopping)"))
            self.pause = False
        if skippable and answer in {"s", "skip"}:
            print(self.dim("    (skipping the rest of the iteration)"))
            self.skipping = True

    def _ask(self, prompt: str) -> str:
        """One answer: a single key press on a real console, a line from a
        pipe — so the tests and anything scripted still type ``s`` + Enter."""
        if not sys.stdin.isatty():
            answer = input(self.dim(f"\n    ── {prompt} "))
            # A pipe does not echo the Enter, so the next step would otherwise
            # land on the same line as the prompt.
            print()
            return answer
        print(self.dim(f"\n    ── {prompt} "), end="", flush=True)
        key = _read_key()
        print("\n")
        return "" if key in ("\r", "\n") else key


def _read_key() -> str:
    """One key from the console, without waiting for Enter."""
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):          # arrows and F-keys send two codes
            msvcrt.getwch()
            return ""
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if key == "\x03":
        raise KeyboardInterrupt
    if key in ("\x04", "\x1a"):
        raise EOFError
    return key


def _wrap(text: str, width: int) -> list:
    """Wrap on spaces, but never inside a formula that has no spaces to break."""
    out, line = [], ""
    for word in text.split(" "):
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    out.append(line)
    return out or [""]


def supports_colour(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name == "nt":
        # Python enables virtual-terminal processing on Windows 10+ consoles;
        # ANSICON and Windows Terminal set these when it is older.
        return bool(os.environ.get("WT_SESSION") or os.environ.get("ANSICON")
                    or sys.getwindowsversion().major >= 10)
    return True


# --------------------------------------------------------------------------- #
#  Choosing a problem
# --------------------------------------------------------------------------- #

def _read_choice(con: Console, prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        con.say()
        raise SystemExit(0)


def choose_problem(con: Console) -> str:
    """The menu: a built-in problem, the Problem 3 group, or data typed in.

    Returns an alias, ``"hw3"`` for the Problem 3 sub-menu, or ``"new"``. Any
    shortcut (``hw3-mask-1``…) typed here is taken as it stands.
    """
    con.title("(s, Q) iterative algorithm — stochastic demand, constant lead time")
    con.say()
    con.say("  Pick a problem to work through:")
    con.say()
    entries = [("hw1", ALIASES["hw1"]), ("hw2", ALIASES["hw2"]),
               ("hw3", PROBLEM_3_LABEL)]
    for i, (_alias, label) in enumerate(entries, 1):
        con.say(f"    {con.bold(str(i))}. {label}")
    con.say(f"    {con.bold(str(len(entries) + 1))}. Enter a new problem")
    con.say()
    while True:
        raw = _read_choice(con, "  Choice [1]: ")
        if not raw:
            return entries[0][0]
        if raw.lower() in ALIASES or raw.lower() == "hw3":
            return raw.lower()
        if raw.lower() in {"new", "n"}:
            return "new"
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(entries):
                return entries[i - 1][0]
            if i == len(entries) + 1:
                return "new"
        con.say(con.red(f"  {raw!r} is not one of the choices."))


def choose_problem_3(con: Console) -> str:
    """The six cases of Problem 3: three products, two scenarios each."""
    con.title("Homework 2, Problem 3 — an ophthalmologist's office")
    con.say()
    con.say("  A = $54 an order, carrying charge 25 %/year, lead time 3 weeks,")
    con.say("  Policy 2 reviews once a month. Scenario 1: 98 % cycle service level;")
    con.say("  Scenario 2: backorder cost 30 % of the unit price.")
    con.say()
    keys = list(PROBLEM_3.items())
    for i, (alias, key) in enumerate(keys, 1):
        short = key.split("Problem 3 — ", 1)[-1]
        con.say(f"    {con.bold(str(i))}. {short}  {con.dim('(' + alias + ')')}")
    con.say()
    while True:
        raw = _read_choice(con, "  Choice [1]: ").lower()
        if not raw:
            return keys[0][0]
        if raw in PROBLEM_3:
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1][0]
        con.say(con.red(f"  {raw!r} is not one of the choices."))


def _ask(prompt: str, default=None, cast=float):
    """One field, with its default in the prompt. Blank takes the default."""
    shown = f" [{default}]" if default is not None else ""
    while True:
        try:
            raw = input(f"    {prompt}{shown}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(0)
        if not raw and default is not None:
            return default
        try:
            value = cast(raw.replace(",", "").replace("_", ""))
        except (TypeError, ValueError):
            print(f"      not a number: {raw!r}")
            continue
        if cast is float and not math.isfinite(value):
            print("      that has to be an ordinary number")
            continue
        return value


def _ask_choice(prompt: str, options: list, default: str) -> str:
    """One of ``options``: an exact name (any case) or an unambiguous start."""
    joined = "/".join(options)
    while True:
        try:
            raw = input(f"    {prompt} ({joined}) [{default}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(0)
        if not raw:
            return default
        exact = [o for o in options if o.lower() == raw]
        if exact:
            return exact[0]
        matches = [o for o in options if o.lower().startswith(raw)]
        if len(matches) == 1:
            return matches[0]
        print(f"      pick one of: {joined}")


#: The stockout bases as the prompt offers them. ``B2v`` is B2 with p entered
#: as a share of the unit cost (p = b·v), which `derive` works out.
STOCKOUT_CHOICES = [
    ("B2", "backorder cost p per unit short (the default)"),
    ("B2v", "backorder cost as a share of the unit cost, p = b·v"),
    ("B1", "cost B₁ per stockout occasion, however many units are short"),
    ("alpha", "service level, Type I:  S(r, Q) ≈ G(r) = α"),
    ("beta", "service level, Type II:  S(r, Q) ≈ 1 − B(r)/Q = β"),
]


def ask_problem(con: Console) -> dict:
    """Build a problem spec from answers typed at the prompt.

    The spec is the same shape ``EXAMPLES`` uses, so everything downstream
    treats a typed problem and a built-in one identically.
    """
    con.heading("New problem — time units")
    base = _ask_choice("Rates are per", list(UNITS), "year")
    spec = {"base_unit": base, "lead_unit": base}

    con.heading("New problem — lead time")
    spec["lead_unit"] = _ask_choice("Lead time is given in", list(UNITS), base)
    spec["lead_value"] = _ask(f"Lead time, in {unit_plural(spec['lead_unit'])}", 2.0)
    spec["lead_time"] = convert(spec["lead_value"], spec["lead_unit"], base)

    con.heading("New problem — costs")
    spec["A"] = _ask("Ordering cost  A  ($ per replenishment)", 15.0)

    derive_spec = {}
    con.say("    How is running out priced, or bounded?")
    for key, words in STOCKOUT_CHOICES:
        con.say(f"      {key:<6} {words}")
    basis = _ask_choice("Stockout basis", [k for k, _w in STOCKOUT_CHOICES], "B2")
    spec["p"] = 0.0          # read only under B2
    if basis == "B2":
        spec["p"] = _ask("Penalty cost  p  ($ per unit short)", 7.0)
        spec["stockout"] = {"mode": "B2"}
    elif basis == "B2v":
        b = _ask("Share of the unit cost  b  (0.30 for 30 %)", 0.3)
        derive_spec["penalty"] = {"mode": "fraction", "b": b}
        spec["stockout"] = {"mode": "B2"}
    else:
        field = STOCKOUT_MODES[basis]["fields"][0]
        value = _ask(f"{field['label']}  {field['symbol']}", field["default"])
        spec["stockout"] = {"mode": basis, "value": value}

    how_h = _ask_choice("Holding cost given as", ["direct", "rate"], "rate")
    if how_h == "rate":
        v = _ask("Unit cost  v  ($ per unit)", 6.0)
        rate = _ask("Carrying charge  r  ($/$ per unit time)", 0.3)
        rate_unit = _ask_choice("That charge is per", list(UNITS), base)
        derive_spec["holding"] = {"mode": "rate", "v": v,
                                  "carrying_rate": rate, "rate_unit": rate_unit}
        spec["v"] = v
        spec["h"] = 0.0      # replaced by the derivation
    else:
        spec["h"] = _ask(f"Holding cost  h  ($ per unit per {unit_label(base)})", 2.0)
        spec["v"] = _ask("Unit cost  v  (0 if it does not matter)", 0.0)

    con.heading("New problem — demand")
    how_d = _ask_choice("Lead-time demand given as", ["period", "direct"], "period")
    if how_d == "period":
        period = _ask_choice("Demand is recorded per", list(UNITS), base)
        per = unit_label(period)
        law = _ask_choice(f"Demand per {per} follows", list(PERIOD_DISTRIBUTIONS),
                          "Normal")
        block = {"mode": "period", "dist": law, "period_unit": period}
        if law == "Normal":
            block["mean"] = _ask(f"Mean demand per {per}", 28.0)
            block["sigma"] = _ask(f"Standard deviation per {per}", 8.0)
        elif law == "Uniform":
            block["lo"] = _ask(f"Lowest demand per {per}", 0.25)
            block["hi"] = _ask(f"Highest demand per {per}", 1.0)
        else:
            block["mean"] = _ask(f"Mean demand per {per}", 0.1)
        derive_spec["demand"] = block
        spec["D"] = 0.0      # replaced by the derivation
        spec["dist_name"] = law
        spec["dist_params"] = {}
    else:
        spec["D"] = _ask(f"Demand rate  D  (units per {unit_label(base)})", 800.0)
        names = list(DISTRIBUTIONS)
        spec["dist_name"] = _ask_choice("Lead-time demand distribution",
                                        names, "Normal")
        params = {}
        for key, label, default in DISTRIBUTIONS[spec["dist_name"]]["fields"]:
            params[key] = _ask(f"{spec['dist_name']}: {label}", default)
        spec["dist_params"] = params

    con.heading("New problem — Policy 2 (optional)")
    con.say("    Policy 2 reviews stock every T and orders up to S. Give T to have")
    con.say("    it worked out too and compared with the (r, Q) policy.")
    if _ask_choice("Also work out Policy 2", ["yes", "no"], "no") == "yes":
        T_unit = _ask_choice("The review period is given in", list(UNITS), base)
        T = _ask(f"Review period  T, in {unit_plural(T_unit)}", 1.0)
        spec["periodic"] = {"T": T, "T_unit": T_unit}

    spec["derive"] = derive_spec or None
    spec["expected"] = ""
    return spec


# --------------------------------------------------------------------------- #
#  The walkthrough
# --------------------------------------------------------------------------- #

def build(spec: dict) -> tuple:
    """Turn a problem spec into ``Inputs`` plus the derivation behind them.

    Whatever the derivation worked out — h, v, D, the lead-time law and its
    parameters, p = b·v — takes the place of the number in the spec, and the
    spec's stockout block sets the basis, exactly as ``example_inputs`` does.
    """
    base = spec.get("base_unit", "year")
    lead_in_base = spec["lead_time"]
    worked = derive(spec.get("derive"), base, lead_in_base, v=spec.get("v"))

    h = worked.h if worked.h is not None else spec["h"]
    v = worked.v if worked.v is not None else spec.get("v", 0.0)
    D = worked.D if worked.D is not None else spec["D"]
    p = worked.p if worked.p is not None else spec.get("p", 0.0)
    # The derived law, whatever it is: Normal, Uniform or Exponential.
    dist = worked.distribution()
    if dist is None:
        dist = build_distribution(spec["dist_name"], spec["dist_params"])

    inp = Inputs(D=D, A=spec["A"], h=h, p=p,
                 lead_time=lead_in_base, dist=dist, v=v)
    stockout = spec.get("stockout") or {}
    mode = stockout.get("mode", "B2")
    if mode != "B2":
        inp.stockout = mode
        setattr(inp, mode, float(stockout["value"]))
    return inp, worked


def review_period(spec: dict):
    """Policy 2's review period in the base unit, or None when there is none."""
    periodic = spec.get("periodic")
    if not periodic:
        return None
    base = spec.get("base_unit", "year")
    return convert(float(periodic["T"]), periodic.get("T_unit") or base, base)


def show_iteration_table(con: Console, iterations: list, headers: list):
    """All completed iterations, one line each, independent of which passes
    were already explained step by step above this table."""
    first, last = iterations[0].index, iterations[-1].index
    span = f"{first}" if first == last else f"{first} … {last}"
    con.heading(f"Iterations {span}, in brief")
    # t, Q_t, r_t, n(r_t), Q_t+1, |Δr|: the columns that move.
    cols = [headers[i] for i in (0, 1, 4, 5, 6, 7)]
    widths = [max(6, len(cols[0]))] + [max(12, len(c)) for c in cols[1:]]
    con.say(con.dim("    " + "  ".join(c.rjust(w) for c, w in zip(cols, widths))))
    for it in iterations:
        delta = "—" if math.isnan(it.delta_r) else f"{it.delta_r:.3f}"
        cells = [str(it.index), f"{it.Q:.3f}", f"{it.r:.3f}", f"{it.n_r:.3f}",
                 f"{it.Q_next:.3f}", delta]
        con.say("    " + "  ".join(c.rjust(w) for c, w in zip(cells, widths)))


def _pdf(dist, x: float):
    """The density of lead-time demand at x, for the B1 check; None when the
    law is discrete (its condition is an inequality, not an equation)."""
    if dist.name == "Normal":
        return dist.pdf(x)
    if dist.name == "Uniform":
        return 1.0 / (dist.b - dist.a) if dist.a <= x <= dist.b else 0.0
    if dist.name == "Exponential":
        return dist.lam * math.exp(-dist.lam * x) if x >= 0.0 else 0.0
    return None


def _show_data(con: Console, spec: dict, base: str):
    """Section 0: the numbers exactly as the problem states them."""
    con.kv("Ordering cost  A", report.fmt(spec["A"], 4), "$ per replenishment")
    given = spec.get("derive") or {}
    stockout = spec.get("stockout") or {}
    mode = stockout.get("mode", "B2")
    if mode == "B2" and given.get("penalty", {}).get("mode") == "fraction":
        con.kv("Backorder cost as a share of v  b",
               report.fmt(given["penalty"]["b"], 4), "p = b·v, $ per unit short")
    elif mode == "B2":
        con.kv("Penalty cost  p", report.fmt(spec["p"], 4), "$ per unit short")
    elif mode == "B1":
        con.kv("Cost per stockout occasion  B₁", report.fmt(stockout["value"], 4),
               "$ each time a cycle runs out")
    elif mode == "alpha":
        con.kv("Cycle service level  α", report.fmt(stockout["value"], 4),
               "P(no stockout in a cycle)")
    else:
        con.kv("Fill rate  β", report.fmt(stockout["value"], 4),
               "fraction of demand met from stock")
    lead_unit = spec.get("lead_unit", base)
    con.kv("Lead time  l", report.fmt(spec.get("lead_value", spec["lead_time"]), 4),
           unit_plural(lead_unit))
    if given.get("holding", {}).get("mode") == "rate":
        hs = given["holding"]
        con.kv("Unit cost  v", report.fmt(hs["v"], 4), "$ per unit")
        con.kv("Carrying charge  r", report.fmt(hs["carrying_rate"], 4),
               f"$/$ per {unit_label(hs.get('rate_unit', base))}")
    else:
        con.kv(f"Holding cost  h", report.fmt(spec["h"], 6),
               f"$ per unit per {unit_label(base)}")
    if given.get("demand", {}).get("mode") == "period":
        ds = given["demand"]
        per = unit_label(ds.get("period_unit", base))
        law = ds.get("dist") or "Normal"
        if law == "Uniform":
            con.kv(f"Lowest demand per {per}", report.fmt(ds["lo"], 4), "units, uniform")
            con.kv(f"Highest demand per {per}", report.fmt(ds["hi"], 4), "units, uniform")
        elif law == "Exponential":
            con.kv(f"Mean demand per {per}", report.fmt(ds["mean"], 4),
                   "units, exponential")
        else:
            con.kv(f"Mean demand per {per}", report.fmt(ds["mean"], 4), "units")
            con.kv(f"Standard deviation per {per}", report.fmt(ds["sigma"], 4), "units")
    else:
        con.kv("Demand rate  D", report.fmt(spec["D"], 4),
               f"units per {unit_label(base)}")
    periodic = spec.get("periodic")
    if periodic:
        T_unit = periodic.get("T_unit") or base
        con.kv("Review period  T  (Policy 2)", report.fmt(float(periodic["T"]), 4),
               unit_plural(T_unit) if float(periodic["T"]) != 1.0 else unit_label(T_unit))


def _show_model(con: Console, mode: str):
    """Section 2: the cost function and the conditions, for this basis."""
    if mode == "B2":
        con.heading("2.  The model, and the two equations being iterated")
        con.say("    Cost per unit time, with p charged per unit short:")
        con.say()
        con.say("        Y(Q, r) = h(Q/2 + r − D·l) + A·D/Q + p·D·n(r)/Q + D·v")
        con.say()
        con.say("    Setting both partial derivatives to zero gives the pair:")
        con.say()
        con.say("        (1)  Q = sqrt( 2·D·[A + p·n(r)] / h )")
        con.say("        (2)  1 − G(r) = Q·h / (p·D)")
        con.say()
        con.say("    n(r) = E[max(X − r, 0)] is the expected shortage per cycle and G")
        con.say("    is the cdf of demand during the lead time. Start at Q = EOQ, read")
        con.say("    r off (2), get a new Q from (1), and repeat until r stops moving.")
    elif mode == "B1":
        con.heading("2.  The model, and the two equations being iterated")
        con.say("    Cost per unit time, with B₁ charged each time a cycle runs out")
        con.say("    (slide 15), however many units are short:")
        con.say()
        con.say("        Y(Q, r) = h(Q/2 + r − D·l) + A·D/Q + B₁·(D/Q)·(1 − G(r)) + D·v")
        con.say()
        con.say("    Setting both partial derivatives to zero gives the pair:")
        con.say()
        con.say("        (1')  Q = sqrt( 2·D·[A + B₁·(1 − G(r))] / h )")
        con.say("        (2')  g(r) = Q·h / (B₁·D)")
        con.say()
        con.say("    G is the cdf of demand during the lead time and g its density;")
        con.say("    the root of (2') is taken on the right tail, where the density")
        con.say("    falls. Start at Q = EOQ, read r off (2'), get a new Q from (1'),")
        con.say("    and repeat until r stops moving.")
    else:
        alpha = mode == "alpha"
        con.heading("2.  The model, and the two conditions that fix Q and r")
        con.say("    A service level is a constraint, not a price, so the cost has no")
        con.say("    stockout term:")
        con.say()
        con.say("        Y(Q, r) = h(Q/2 + r − D·l) + A·D/Q + D·v")
        con.say()
        con.say("    The textbook's sequential approach: Q first, then r.")
        con.say()
        con.say("        (1)  Q = EOQ = sqrt( 2·A·D / h )")
        if alpha:
            con.say("        (2)  G(r) = α,  so  r = G⁻¹(α)")
            con.say()
            con.say("    α is the chance a replenishment cycle does not run out; G is")
            con.say("    the cdf of demand during the lead time.")
        else:
            con.say("        (2)  n(r) = (1 − β)·Q")
            con.say()
            con.say("    β is the fraction of demand met from stock; n(r) is the expected")
            con.say("    shortage per cycle, so (1 − β)·Q is the shortage allowed.")
        con.say("    Q does not depend on r here, so there is no iteration: one pass")
        con.say("    settles both.")


def _check_rows(inp, res) -> list:
    """Section 7: (equation, left side, right side) at the answer."""
    D, A, h, Q, r = inp.D, inp.A, inp.h, res.Q, res.r
    mode = inp.stockout
    if mode == "B2":
        return [("(1)  Q = sqrt(2D[A + p·n(r)]/h)", Q,
                 math.sqrt(2.0 * D * (A + inp.p * res.n_r) / h)),
                ("(2)  1 − G(r) = Q·h/(p·D)", 1.0 - inp.dist.cdf(r),
                 Q * h / (inp.p * D))]
    if mode == "B1":
        rows = [("(1') Q = sqrt(2D[A + B₁(1 − G(r))]/h)", Q,
                 math.sqrt(2.0 * D * (A + inp.B1 * (1.0 - inp.dist.cdf(r))) / h))]
        density = _pdf(inp.dist, r)
        if density is not None:
            rows.append(("(2') g(r) = Q·h/(B₁·D)", density, Q * h / (inp.B1 * D)))
        return rows
    rows = [("(1)  Q = EOQ = sqrt(2AD/h)", Q, inp.eoq)]
    if mode == "alpha":
        rows.append(("(2)  G(r) = α", inp.dist.cdf(r), inp.alpha))
    else:
        rows.append(("(2)  n(r) = (1 − β)·Q", res.n_r, (1.0 - inp.beta) * Q))
    return rows


def walk(con: Console, label: str, spec: dict, tol: float, max_iter: int,
         single_pass: bool, excel_path: str | None = None) -> int:
    base = spec.get("base_unit", "year")
    con.title(label)
    if spec.get("expected"):
        con.note(spec["expected"])

    # ---- what was given ---------------------------------------------------- #
    con.heading("0.  The data as the problem states it")
    _show_data(con, spec, base)
    con.wait()

    inp, worked = build(spec)
    mode = inp.stockout
    lead_unit = spec.get("lead_unit", base)
    T = review_period(spec)

    # ---- part (a): the conversions ----------------------------------------- #
    if worked.used:
        con.heading("1.  What has to be worked out before the iteration can start")
        con.say("    The cost function wants a holding cost per unit per unit time")
        con.say("    and the distribution of demand over the lead time. Neither is")
        con.say("    given directly, so each is built first.")
        if worked.p is not None:
            con.say("    The penalty cost comes as a share of the unit cost, so it is")
            con.say("    worked out too.")
        con.wait()
        for i, step in enumerate(worked.steps, 1):
            con.step(f"1.{i}", step["label"], step["plain"])
            con.wait()

    # ---- the model --------------------------------------------------------- #
    _show_model(con, mode)
    con.wait()

    con.heading("3.  The data the iteration actually sees")
    units_block = {
        "base": base, "base_label": unit_label(base),
        "lead": lead_unit, "lead_label": unit_label(lead_unit),
        "lead_entered": spec.get("lead_value", spec["lead_time"]),
        "lead_in_base": inp.lead_time,
    }
    for name, value in report.input_rows_for(inp, units_block):
        con.kv(name, value)
    if T is not None:
        given_T = spec["periodic"]
        T_unit = given_T.get("T_unit") or base
        shown = f"{report.fmt(float(given_T['T']), 4)} {unit_label(T_unit)}"
        if T_unit != base:
            shown += f" = {report.fmt(T, 6)} {unit_plural(base)}"
        con.kv("Review period  T  (Policy 2)", shown)
    con.wait()

    # ---- the iteration ----------------------------------------------------- #
    res = solve_rq(inp, tol=tol, max_iter=max_iter, single_pass=single_pass)
    headers = report.iteration_headers(res)

    if mode in ("alpha", "beta"):
        con.heading("4.  Q and r, worked out once — there is no iteration")
        if mode == "alpha":
            con.say("    Under a cycle service level Q is the EOQ and r = G⁻¹(α): Q does")
        else:
            con.say("    Under a fill rate Q is the EOQ and r solves n(r) = (1 − β)·Q: Q does")
        con.say("    not depend on r, so one pass gives both and nothing is iterated.")
        con.wait()
        it = res.iterations[0]
        for i, step in enumerate(pass_steps(inp, it, 0), 1):
            con.step(f"4.{i}", step["label"], step["plain"])
            con.wait()
        con.say("    The single row of the table, column by column:")
        for head, cell in zip(headers, report.iteration_rows(res)[0]):
            con.kv(head, cell)
        con.wait()
    else:
        b1 = mode == "B1"
        eq1, eq2 = ("(1')", "(2')") if b1 else ("(1)", "(2)")
        middle = "1 − G" if b1 else "n"
        con.heading("4.  The iteration, one step at a time")
        last = max_iter - 1
        con.say(f"    {'No early stopping (tol = 0)' if tol == 0 else f'Convergence tolerance = {tol:g}'}, "
                f"iteration cap = {max_iter}.")
        con.say(f"    The cap allows at most t = 0{f' … {last}' if last else ''}; "
                "with tol > 0, the solver stops earlier if converged.")
        con.say("    Detailed calculations: the first 3 completed iterations (0, 1, 2).")
        con.say("    Complete summary: EVERY completed iteration, including 0, 1, 2.")
        con.say(con.dim("    Iterations are numbered from 0, as in the lecture: "
                        "iteration t starts"))
        con.say(con.dim(f"    from Q_t (Q0 is the EOQ), finds r_t from {eq2} and "
                        f"{middle}(r_t), then Q_t+1 from {eq1}."))
        con.say(con.dim("    Press s during detailed working to skip explanations; "
                        "the complete iteration table still appears."))
        con.wait(skippable=True)

        # Calculations have ALREADY run to the tolerance/cap in solve_rq().
        # This is presentation only: expand at most the first three passes.
        for it in res.iterations[:3]:
            if con.skipping:
                break
            t = it.index
            con.heading(f"Iteration {t}   —   Q{t} → r{t} → {middle}(r{t}) → Q{t + 1}")
            for i, step in enumerate(pass_steps(inp, it, t), 1):
                con.step(f"{t}.{i}", step["label"], step["plain"])
                con.wait(skippable=True)
                if con.skipping:
                    break
        con.skipping = False
        # ALWAYS list 0..last, including the passes whose calculations
        # are already expanded above. A presentation limit is not a solver cap.
        show_iteration_table(con, res.iterations, headers)

    # ---- the verdict ------------------------------------------------------- #
    con.heading("5.  Where it stopped")
    count = len(res.iterations)
    last_t = res.iterations[-1].index
    ran = (f"{count} iteration{'s' if count != 1 else ''} "
           f"(t = 0{f' … {last_t}' if last_t else ''})")
    if mode in ("alpha", "beta"):
        con.para("Nothing to converge: Q is the EOQ and r comes straight from the "
                 "service level, in one pass.", con.green)
    elif single_pass:
        con.say(con.yellow("    Single pass: Q was held at the EOQ and r read off "
                         f"equation {eq2} once, in iteration 0. This is the deck's "
                         "cost-effective approximation, not the fixed point."))
    elif tol == 0:
        con.say(con.yellow(f"    Fixed iteration count completed ({ran}); tolerance 0 "
                             "did not test early convergence."))
    elif res.converged:
        con.say(con.green(f"    The reorder point stopped moving in iteration "
                        f"{last_t}, after {ran}: the last |Δr| was "
                        f"{res.iterations[-1].delta_r:.3f}."))
    else:
        con.say(con.yellow(f"    Stopped after {ran} with |Δr| = "
                         f"{res.iterations[-1].delta_r:.3f}; r was still moving."))
    con.say(f"    So the answer below is {report.answer_source(res)}.")
    for note in res.notes:
        con.note(note)
    con.wait()

    # ---- the answer -------------------------------------------------------- #
    con.heading("6.  The answer")
    for row in report.summary_rows(res):
        con.kv(row["label"], row["value"], row["unit"])
    con.wait()

    # ---- both equations at the answer -------------------------------------- #
    con.heading("7.  Check: both equations hold at the answer")
    for name, lhs, rhs in _check_rows(inp, res):
        gap = abs(lhs - rhs)
        mark = con.green("ok") if gap < 1e-6 else con.yellow(f"difference {gap:.3f} (full precision)")
        con.say(f"    {name.ljust(36)} {lhs:>14.3f}  vs {rhs:>14.3f}   {mark}")
    if inp.dist.discrete:
        con.note("Lead-time demand is discrete, so the condition on r holds as an "
                 "inequality and the two sides need not meet exactly.")
    elif mode == "B1" and inp.dist.name == "Uniform":
        con.note("A uniform density is flat, so (2') cannot hold with equality: r "
                 "sits at a corner of the range instead (see the notes above).")
    elif res.degenerate:
        con.note("r was pinned because its condition has no root (see the notes "
                 "above), so that condition does not hold at the answer.")
    con.wait()

    # ---- the cost ---------------------------------------------------------- #
    con.heading("8.  What that policy costs per unit time")
    for row in report.cost_rows(res):
        con.kv(row["label"], row["value"])
    con.wait("Enter to finish" if T is None else "Enter to continue")

    policy2 = comparison = None
    if T is not None:
        try:
            policy2 = solve_periodic(inp, T)
        except SolverError as exc:
            con.heading("Policy 2 — periodic review (R, S)")
            con.para(f"Policy 2 cannot be worked out: {exc}", con.red)
        else:
            comparison = compare_policies(res, policy2)
            _walk_policy_2(con, inp, spec, base, units_block, policy2, comparison)

    con.heading(f"{13 if comparison else 9}.  In one sentence")
    con.say(f"    Order {res.Q:,.3f} units whenever inventory position (on hand + on order − backorders)")
    con.say(f"    falls to {res.r:,.3f} units. That carries {res.safety_stock:,.3f} "
          f"units of safety")
    con.say(f"    stock above the {inp.theta:,.3f} units expected during the lead time.")
    if comparison is not None:
        per = unit_label(base)
        con.say(f"    Reviewing every {report.fmt(T, 4)} {unit_plural(base)} instead, order up "
                f"to {policy2.S:,.3f} units.")
        if comparison.chosen == "Either":
            con.say("    The two policies cost the same.")
        else:
            other = "Policy 2" if comparison.chosen == "Policy 1" else "Policy 1"
            con.say(f"    {comparison.chosen} is the cheaper: it saves "
                    f"{comparison.difference:,.3f} per {per} over {other}.")
    con.say()
    if excel_path:
        from excel_export import save_payload
        payload = {
            "settings": {"tolerance": tol, "max_iter": max_iter},
            "flags": {"converged": res.converged},
            "answer": {"Q": res.Q, "r": res.r},
            "summary": report.summary_rows(res),
            "inputs": [{"label": a, "value": b} for a, b in report.input_rows(res, units_block)],
            "cost": report.cost_rows(res),
            "iterations": [{"index": it.index, "Q": it.Q, "tail": it.tail,
                             "G": it.G_target, "r": it.r, "n_r": it.n_r,
                             "Q_next": it.Q_next, "delta_r": it.delta_r}
                            for it in res.iterations],
            "steps_by_iteration": [
                {"index": it.index, "steps": pass_steps(inp, it)}
                for it in res.iterations[:3]
            ],
        }
        if policy2 is not None:
            payload["policy2"] = {"summary": report.periodic_summary_rows(policy2, units_block)}
        if comparison is not None:
            payload["comparison"] = {"rows": report.comparison_rows(comparison, units_block)}
        path = save_payload(payload, excel_path)
        con.say(con.green(f"    Excel file saved: {path}"))
    return 0


def _walk_policy_2(con: Console, inp, spec: dict, base: str, units_block: dict,
                   res2, cmp) -> None:
    """Sections 9–12: Policy 2 (order up to S every T) and the comparison."""
    mode = inp.stockout
    bases = unit_plural(base)
    every = periodic_steps(res2)
    # periodic_steps opens with the protection interval (one step when its
    # demand was given directly, two when it is scaled from lead-time demand)
    # and closes with safety stock, average inventory and the cost.
    opening = 1 if math.isnan(res2.factor) else 2
    protection, condition, closing = (every[:opening], every[opening:-3], every[-3:])

    con.heading("9.  Policy 2 — periodic review (R, S): the protection interval")
    con.say("    Instead of watching stock all the time, look at it every T and")
    con.say("    order enough to bring inventory position (on hand + on order − backorders) up to S. An order")
    con.say("    placed at one review arrives L later, and the next chance to order")
    con.say("    is T later still — so S has to cover demand over T + L, the")
    con.say("    protection interval, not over the lead time alone.")
    con.say()
    con.kv("Review period  T", report.fmt(res2.T, 6), bases)
    con.kv("Lead time  L", report.fmt(inp.lead_time, 6), bases)
    con.kv("Protection interval  T + L", report.fmt(res2.protection_interval, 6), bases)
    con.wait()
    for i, step in enumerate(protection, 1):
        con.step(f"9.{i}", step["label"], step["plain"])
        con.wait()
    con.kv("Demand over T + L", res2.protection.describe())
    con.kv("  its mean", report.fmt(res2.protection.mean, 6), "units")
    con.kv("  its standard deviation", report.fmt(res2.protection.stdev, 6), "units")
    con.wait()

    con.heading("10.  Policy 2 — the order-up-to level S from its condition")
    con.say("    Cost per unit time (slide 48), one order every T:")
    con.say()
    term = {"B2": " + p·n(S)/T", "B1": " + B₁·(1 − G(S))/T"}.get(mode, "")
    con.say(f"        Y2(S) = A/T + h(S − D·L − D·T/2){term} + D·v")
    con.say()
    condition_text = {
        "B2": "dY2/dS = 0 gives  G(S) = 1 − h·T/p  (slide 49)",
        "B1": "dY2/dS = 0 gives  g(S) = h·T/B₁, on the right tail",
        "alpha": "the service level sets it directly:  G(S) = α",
        "beta": "the fill rate sets it:  n(S) = (1 − β)·D·T",
    }[mode]
    con.para(f"n and G belong to demand over T + L; {condition_text}.")
    con.wait()
    for i, step in enumerate(condition, 1):
        con.step(f"10.{i}", step["label"], step["plain"])
        con.wait()
    for note in res2.notes:
        con.note(note)

    con.heading("11.  Policy 2 — the answer and what it costs")
    for i, step in enumerate(closing, 1):
        con.step(f"11.{i}", step["label"], step["plain"])
        con.wait()
    for row in report.periodic_summary_rows(res2, units_block):
        con.kv(row["label"], row["value"], row["unit"])
    con.say()
    for row in report.periodic_cost_rows(res2):
        con.kv(row["label"], row["value"])
    con.wait()

    con.heading("12.  Policy 1 against Policy 2")
    con.say(f"    Both costs per {unit_label(base)}, on the same terms and without the")
    con.say("    purchase cost D·v, which is the same whichever policy is used.")
    con.say()
    for row in report.comparison_rows(cmp, units_block):
        con.kv(row["label"], row["value"], row["unit"])
    if base != "year":
        per_year = convert(1.0, "year", base)          # 52 weeks, 12 months …
        con.kv("Per year: Policy 1 / Policy 2",
               f"{cmp.policy1 * per_year:,.3f} / {cmp.policy2 * per_year:,.3f}",
               f"× {per_year:g} {bases}")
    con.say()
    if cmp.chosen == "Either":
        con.say(con.bold("    The two policies cost the same."))
    else:
        name = ("continuous review (r, Q)" if cmp.chosen == "Policy 1"
                else "periodic review (R, S)")
        con.para(f"Choose {cmp.chosen}, {name}: it costs {cmp.difference:,.3f} "
                 f"less per {unit_label(base)}.", con.green)
    for note in cmp.notes:
        con.note(note)
    con.wait("Enter to finish")


# --------------------------------------------------------------------------- #

def spec_for(choice: str, con: Console) -> tuple:
    if choice == "new":
        return "A problem of your own", ask_problem(con)
    key = ALIASES[choice]
    spec = dict(EXAMPLES[key])
    return key, spec


def main(argv=None) -> int:
    keys = ", ".join(ALIASES)
    parser = argparse.ArgumentParser(
        description="Walk the (s, Q) iteration one step at a time: the stockout "
                    "basis the problem uses (p, B1, alpha or beta) and, when it "
                    "gives a review period, Policy 2 and the cheaper policy.",
        epilog="Problem 3 keys: hw3-<mask|sanitizer|gown>-<1|2>; scenario 1 is "
               "the 98% cycle service level, scenario 2 the backorder cost of "
               "30% of v. 'hw3' alone opens a menu of the six.")
    parser.add_argument("--problem", "-p", default=None,
                        help=f"one of {keys}; hw3 for the Problem 3 menu; "
                             "or 'new' to type one in")
    parser.add_argument("--no-pause", action="store_true",
                        help="print everything without waiting for Enter")
    parser.add_argument("--no-color", action="store_true", help="plain text only")
    parser.add_argument("--ascii", action="store_true",
                        help="ASCII only, for a console that cannot show "
                             "box-drawing characters or Greek letters")
    parser.add_argument("--max-iter", type=int, default=200,
                        help="stop after this many passes (Problem 1 asks for 3)")
    parser.add_argument("--tol", type=float, default=1e-2,
                        help="stopping tolerance (0 = run exactly --max-iter passes)")
    parser.add_argument("--excel", metavar="PATH", default=None,
                        help="write an Excel .xlsx workbook with every iteration")
    parser.add_argument("--single-pass", action="store_true",
                        help="the deck's approximation: one r off the EOQ")
    args = parser.parse_args(argv)

    unicode_ok = _prepare(sys.stdout) and not args.ascii
    con = Console(colour=not args.no_color and supports_colour(sys.stdout),
                  pause=not args.no_pause, unicode_ok=unicode_ok)

    choice = args.problem
    if choice is None:
        choice = choose_problem(con)
    choice = choice.lower()
    if choice not in ALIASES and choice not in ("new", "hw3"):
        print(f"Unknown problem {choice!r}. Choose one of: "
              + keys + ", hw3, new", file=sys.stderr)
        return 2

    if args.max_iter < 1:
        print("--max-iter must be at least 1", file=sys.stderr)
        return 2
    if not 0 <= args.tol <= 1:
        print("--tol must be in [0, 1]", file=sys.stderr)
        return 2

    if choice == "hw3":
        choice = choose_problem_3(con)

    try:
        label, spec = spec_for(choice, con)
        return walk(con, label, spec, tol=args.tol, max_iter=args.max_iter,
                    single_pass=args.single_pass, excel_path=args.excel)
    except SolverError as exc:
        con.say()
        print(con.red(f"  No answer: {exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
