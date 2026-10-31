"""The web layer of the (r, Q) solver: a small JSON API plus the static page.

Nothing here runs on its own. ``app_desktop.py`` (next to this file) calls
``serve_in_background`` to show the page in a window; ``app_desktop.py --browser`` starts the same server for browser usage. Standard library only. The page
in web/ (found next to this file, whatever the working directory) talks to:

    GET  /api/meta    the field list, the distributions and the homework problems
    POST /api/solve        one set of inputs in, one solved report out
    POST /api/export-xlsx  save the workbook directly inside run/
    GET  /health      "ok", for container health checks
"""

from __future__ import annotations

import json
import math
import mimetypes
import posixpath
import socketserver
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import report
from derive import DERIVE_FIELDS, derive
from steps import pass_steps, periodic_steps
from timeunits import UNITS, convert
from rq_solver import (
    DISTRIBUTIONS, EXAMPLES, STOCKOUT_MODES, Inputs, SolverError,
    build_distribution, compare_policies, solve_periodic, solve_rq,
)

# Always save GUI exports beside the Python source, not to Downloads or the
# current working directory.  The filename is fixed, never user-controlled.
RUN_ROOT = Path(__file__).resolve().parent
WEB_ROOT = (RUN_ROOT / "web").resolve()
EXCEL_OUTPUT = RUN_ROOT / "rq_iteration_results.xlsx"
MAX_BODY = 64 * 1024          # a solve request is a few hundred bytes
TOLERANCES = [0, 1e-2, 1e-4, 1e-6, 1e-8, 1e-10, 1e-12]

#: The calendar now lives in `timeunits` so the derivation module and the
#: terminal walkthrough can convert without importing the web layer. Both names
#: stay exported from here, because that is where every caller already looks.

BASE_FIELDS = [
    {"key": "D", "label": "Demand rate", "symbol": "D", "default": 800.0,
     "per_base": True, "help": "Demand per base time unit."},
    {"key": "A", "label": "Ordering cost", "symbol": "A", "default": 10.0,
     "help": "Fixed cost of placing one replenishment."},
    {"key": "h", "label": "Holding cost", "symbol": "h", "default": 2.0,
     "per_base": True, "help": "Cost of carrying one unit for one base time unit."},
    {"key": "p", "label": "Penalty cost", "symbol": "p", "default": 5.0,
     "help": "Cost charged per unit short."},
    {"key": "lead_time", "label": "Lead time", "symbol": "l",
     "default": 2.0, "unit": "lead",
     "help": "Give it in whatever unit suits; it is converted into the base "
             "unit before the model sees it."},
    {"key": "v", "label": "Unit cost", "symbol": "v", "default": 0.0,
     "help": "Optional. Shifts the total cost by D·v and nothing else."},
]

#: Policy 2's one extra input. The review period carries its own unit, like
#: the lead time: Problem 3 reviews monthly on a weekly model.
PERIODIC_FIELDS = [
    {"key": "T", "label": "Review period", "symbol": "T", "default": 1.0,
     "unit": "review",
     "help": "Policy 2 reviews stock every T and orders up to S. Given in any "
             "unit; it is converted into the base unit like the lead time."},
]


# --------------------------------------------------------------------------- #
#  Payload helpers
# --------------------------------------------------------------------------- #

def jsonable(value):
    """JSON has no NaN or Infinity, so they travel as null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def meta_payload() -> dict:
    return {
        "base_fields": BASE_FIELDS,
        "derive_fields": DERIVE_FIELDS,
        "tolerances": TOLERANCES,
        "default_tolerance": 1e-2,
        "units": [{"key": key, **spec} for key, spec in UNITS.items()],
        "default_base_unit": "year",
        "default_lead_unit": "week",
        "distributions": {
            name: {
                "fields": [{"key": k, "label": lab, "default": d}
                           for k, lab, d in meta["fields"]],
                "help": meta["help"],
                "taught": meta["taught"],
            }
            for name, meta in DISTRIBUTIONS.items()
        },
        "examples": {
            key: {
                "label": key,
                "values": {f: spec[f] for f in
                           ("D", "A", "h", "p", "lead_time", "v")},
                "distribution": spec["dist_name"],
                "params": spec["dist_params"],
                "expected": spec["expected"],
                "base_unit": spec.get("base_unit", "year"),
                "lead_unit": spec.get("lead_unit", "week"),
                "lead_value": spec.get("lead_value", spec["lead_time"]),
                #: Present only on the homework problems, which state a
                #: carrying charge and demand per period rather than h and the
                #: lead-time distribution.
                "derive": spec.get("derive"),
                #: Problem 3 only: {"mode", "value"} and {"T", "T_unit"}, in
                #: the shape /api/solve takes them. None means B2 and no
                #: periodic review.
                "stockout": spec.get("stockout"),
                "periodic": spec.get("periodic"),
            }
            for key, spec in EXAMPLES.items()
        },
        "stockout_modes": STOCKOUT_MODES,
        "default_stockout": "B2",
        "periodic_fields": PERIODIC_FIELDS,
        "default_review_unit": "month",
    }


def _number(raw, label: str) -> float:
    if isinstance(raw, bool) or raw is None:
        raise SolverError(f"{label} is missing.")
    if isinstance(raw, str):
        raw = raw.strip().replace(",", "")
        if not raw:
            raise SolverError(f"{label} is empty.")
        # "2/52" is how a lead time of two weeks in a yearly model gets written.
        if "/" in raw:
            top, _, bottom = raw.partition("/")
            try:
                numerator, denominator = float(top), float(bottom)
            except ValueError:
                raise SolverError(f"{label} is not a number: {raw!r}") from None
            if denominator == 0:
                raise SolverError(f"{label} divides by zero.")
            return numerator / denominator
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise SolverError(f"{label} is not a number: {raw!r}") from None
    return value


def solve_payload(body: dict) -> dict:
    if not isinstance(body, dict):
        raise SolverError("The request body must be a JSON object.")

    # The stockout basis decides whether p is needed at all: B1, alpha and beta
    # read their own number, and p = b·v derives it.
    stockout = _stockout(body.get("stockout"))
    mode = stockout[0] if stockout else "B2"
    derive_spec = body.get("derive")
    p_derived = (isinstance(derive_spec, dict)
                 and isinstance(derive_spec.get("penalty"), dict)
                 and derive_spec["penalty"].get("mode") == "fraction")

    values = {}
    for field in BASE_FIELDS:
        raw = body.get(field["key"])
        if (field["key"] == "p" and (mode != "B2" or p_derived)
                and (raw is None or (isinstance(raw, str) and not raw.strip()))):
            values["p"] = 0.0
            continue
        values[field["key"]] = _number(raw, field["label"])

    # D, h and the lead time have to share one unit; the caller names the unit
    # each was entered in and the lead time is converted into the base.
    base_unit = body.get("base_unit") or "year"
    lead_unit = body.get("lead_unit") or base_unit
    for name, label in ((base_unit, "base time unit"), (lead_unit, "lead-time unit")):
        if name not in UNITS:
            raise SolverError(f"Unknown {label}: {name!r}")
    lead_entered = values["lead_time"]
    values["lead_time"] = convert(lead_entered, lead_unit, base_unit)

    dist_spec = body.get("dist") or {}
    name = dist_spec.get("name")
    if name not in DISTRIBUTIONS:
        raise SolverError(f"Unknown lead-time demand distribution: {name!r}")

    # Whatever the caller asked to have worked out first — h from a carrying
    # charge, the lead-time distribution from demand per period. Each one it
    # returns replaces the field the form would otherwise have sent, and the
    # working is prepended to the steps so the page shows it above the
    # iteration rather than presenting the numbers as if they were given.
    worked = derive(derive_spec, base_unit, values["lead_time"], v=values["v"])
    if worked.h is not None:
        values["h"] = worked.h
    if worked.v is not None:
        values["v"] = worked.v
    if worked.D is not None:
        values["D"] = worked.D
    if worked.p is not None:
        values["p"] = worked.p

    params = {}
    if worked.dist_name is not None:
        # Per-period demand carries its own law (Normal unless the derive
        # block says Uniform or Exponential), and the lead-time demand it
        # gives is of that law. A different choice on the form is a
        # contradiction, so say so rather than pick one silently.
        if name != worked.dist_name:
            article = "an" if worked.dist_name[0] in "AEIOU" else "a"
            raise SolverError(
                f"Demand per period was given as {worked.dist_name}, so the "
                f"lead-time demand derived from it is {article} "
                f"{worked.dist_name.lower()} one — not {name}. Choose "
                f"{worked.dist_name} as the distribution, or enter the {name} "
                "parameters directly instead.")
        params = dict(worked.dist_params)
    else:
        for key, label, _default in DISTRIBUTIONS[name]["fields"]:
            params[key] = _number((dist_spec.get("params") or {}).get(key),
                                  f"{name}: {label}")

    tol = _number(body.get("tol", 1e-2), "Tolerance")
    if not 0.0 <= tol <= 1.0:
        raise SolverError("The tolerance must be between 0 and 1 (0 = run the full iteration cap).")
    max_iter = _number(body.get("max_iter", 200), "Maximum iterations")
    if max_iter != int(max_iter) or not 1 <= max_iter <= 100_000:
        raise SolverError("Maximum iterations must be a whole number from 1 to 100000.")
    single_pass = bool(body.get("single_pass", False))

    inputs = Inputs(D=values["D"], A=values["A"], h=values["h"], p=values["p"],
                    lead_time=values["lead_time"],
                    dist=build_distribution(name, params), v=values["v"])
    if stockout and mode != "B2":
        inputs.stockout = mode
        setattr(inputs, mode, stockout[1])
    periodic = _periodic(body.get("periodic"), base_unit)
    res = solve_rq(inputs, tol=tol, max_iter=int(max_iter), single_pass=single_pass)
    res2 = cmp = None
    if periodic:
        res2 = solve_periodic(inputs, periodic["T_in_base"])
        cmp = compare_policies(res, res2)

    units_block = {
        "base": base_unit,
        "base_label": UNITS[base_unit]["label"],
        "lead": lead_unit,
        "lead_label": UNITS[lead_unit]["label"],
        "lead_entered": lead_entered,
        "lead_in_base": values["lead_time"],
    }

    payload = {
        "ok": True,
        "answer": {
            "Q": res.Q, "r": res.r, "n_r": res.n_r,
            "safety_stock": res.safety_stock, "theta": inputs.theta,
            "eoq": inputs.eoq, "fill_rate": res.fill_rate,
            "orders_per_period": res.orders_per_period,
            "cycle_length": res.cycle_length,
        },
        "flags": {
            "converged": res.converged,
            "degenerate": res.degenerate,
            "diverged": res.diverged,
            "single_pass": single_pass,
            "discrete": inputs.dist.discrete,
        },
        "distribution": {"name": name, "describe": inputs.dist.describe(),
                         "mean": inputs.dist.mean, "stdev": inputs.dist.stdev},
        "units": units_block,
        "iterations": [{"index": it.index, "Q": it.Q, "tail": it.tail,
                        "G": it.G_target, "r": it.r, "n_r": it.n_r,
                        "Q_next": it.Q_next, "delta_r": it.delta_r}
                       for it in res.iterations],
        "summary": report.summary_rows(res),
        "inputs": [{"label": lab, "value": val}
                   for lab, val in report.input_rows(res, units_block)],
        "cost": report.cost_rows(res),
        "derivation": worked.steps,
        "steps": pass_steps(inputs, res.iterations[0]),
        "steps_by_iteration": [
            {"index": it.index, "steps": pass_steps(inputs, it)}
            for it in res.iterations[:3]
        ],
        "settings": {"tolerance": tol, "max_iter": int(max_iter)},
        "notes": res.notes,
        "csv": report.to_csv(res, units_block, res2, cmp),
        "text": report.to_text(res, units_block, res2, cmp),
    }

    # Everything below appears only when the request asked for it, so a
    # request that names neither a stockout basis nor a review period gets
    # back exactly the bytes it always did.
    if stockout:
        if mode == "B1":
            for row, it in zip(payload["iterations"], res.iterations):
                row["x"] = it.density_target
        payload["stockout"] = {
            "mode": mode,
            "label": STOCKOUT_MODES[mode]["label"],
            "symbol": STOCKOUT_MODES[mode]["symbol"],
            "value": inputs.stockout_value,
            "cycle_service_level": res.cycle_service_level,
            "stockout_probability": res.stockout_probability,
            "fill_rate": res.fill_rate,
            "iteration_headers": report.iteration_headers(res),
        }
    if res2 is not None:
        payload["policy2"] = {
            "T": periodic["T"],
            "T_unit": periodic["T_unit"],
            "T_in_base": res2.T,
            "factor": res2.factor,
            "protection": {"name": res2.protection.name,
                           "describe": res2.protection.describe(),
                           "params": res2.protection.params(),
                           "mean": res2.protection.mean,
                           "stdev": res2.protection.stdev},
            "answer": {
                "S": res2.S, "n_S": res2.n_S, "G_S": res2.G_S,
                "target": res2.target,
                "safety_stock": res2.safety_stock,
                "average_inventory": res2.average_inventory,
                "fill_rate": res2.fill_rate,
                "stockout_probability": res2.stockout_probability,
                "orders_per_period": res2.orders_per_period,
                "total_cost": res2.total_cost,
                "cost_excluding_purchase": res2.cost_excluding_purchase,
            },
            "flags": {"degenerate": res2.degenerate,
                      "discrete": res2.protection.discrete},
            "summary": report.periodic_summary_rows(res2, units_block),
            "cost": report.periodic_cost_rows(res2),
            "steps": periodic_steps(res2),
            "notes": res2.notes,
        }
        payload["comparison"] = {
            "policy1": cmp.policy1,
            "policy2": cmp.policy2,
            "purchase": cmp.purchase,
            "policy1_total": cmp.policy1_total,
            "policy2_total": cmp.policy2_total,
            "difference": cmp.difference,
            "chosen": cmp.chosen,
            "base_unit": base_unit,
            "rows": report.comparison_rows(cmp, units_block),
            "notes": cmp.notes,
        }
    return jsonable(payload)


def _stockout(raw):
    """``(mode, value)`` from the request's ``stockout`` block, or None.

    ``{"mode": "alpha", "value": 0.98}``. B2 needs no value — it is the ``p``
    field (or p = b·v) — and ignores one if sent.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SolverError('The stockout block must be a JSON object such as '
                          '{"mode": "alpha", "value": 0.98}.')
    mode = raw.get("mode") or "B2"
    if mode not in STOCKOUT_MODES:
        raise SolverError(f"Unknown stockout basis: {mode!r}. Choose one of "
                          + ", ".join(STOCKOUT_MODES) + ".")
    if mode == "B2":
        return mode, None
    label = STOCKOUT_MODES[mode]["fields"][0]["label"]
    return mode, _number(raw.get("value"), label)


def _periodic(raw, base_unit: str):
    """The review period from the request's ``periodic`` block, or None.

    ``{"T": 1, "T_unit": "month"}``; absent, null, false, or with
    ``"enabled": false``, Policy 2 is off.
    """
    if raw is None or raw is False:
        return None
    if not isinstance(raw, dict):
        raise SolverError('The periodic block must be a JSON object such as '
                          '{"T": 1, "T_unit": "month"}.')
    if raw.get("enabled", True) is False:
        return None
    T = _number(raw.get("T"), "Review period T")
    if not math.isfinite(T) or T <= 0.0:
        raise SolverError("The review period T must be greater than zero.")
    unit = raw.get("T_unit") or base_unit
    if unit not in UNITS:
        raise SolverError(f"Unknown review-period unit: {unit!r}")
    return {"T": T, "T_unit": unit, "T_in_base": convert(T, unit, base_unit)}


# --------------------------------------------------------------------------- #
#  Handler
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):

    server_version = "rq-solver"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    quiet = False
    download_exports = False   # True when hosted publicly (see server.py)

    # -- plumbing ------------------------------------------------------- #
    def log_message(self, fmt, *args):
        if not self.quiet:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body: bytes, content_type: str, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload, extra=None):
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _error(self, status, message):
        self._json(status, {"ok": False, "error": message})

    # -- routes --------------------------------------------------------- #
    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == "/health":
            return self._send(HTTPStatus.OK, b"ok", "text/plain; charset=utf-8")
        if path == "/api/meta":
            return self._json(HTTPStatus.OK, meta_payload())
        if path.startswith("/api/"):
            return self._error(HTTPStatus.NOT_FOUND, f"No endpoint at {path}")
        return self._static(path)

    do_HEAD = do_GET

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/api/solve", "/api/export-xlsx"):
            return self._error(HTTPStatus.NOT_FOUND, f"No endpoint at {path}")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "Content-Length is not a number.")
        if length > MAX_BODY:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                               "That request is too large.")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(HTTPStatus.BAD_REQUEST, "The request body is not JSON.")
        try:
            payload = solve_payload(body)
            if path == "/api/export-xlsx" and self.download_exports:
                # Hosted mode: hand the workbook to the browser as a download
                # instead of writing it on the (shared, ephemeral) server disk.
                from excel_export import export_bytes
                return self._send(
                    HTTPStatus.OK, export_bytes(payload),
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                    extra={"Content-Disposition":
                           f'attachment; filename="{EXCEL_OUTPUT.name}"'})
            if path == "/api/export-xlsx":
                from excel_export import save_payload
                # Desktop WebView2 may silently ignore browser downloads.
                # Save on the local Python side, then confirm the exact path.
                # Repeated exports replace the previous workbook with the latest
                # currently entered inputs.
                try:
                    saved = save_payload(payload, str(EXCEL_OUTPUT))
                except PermissionError:
                    return self._error(HTTPStatus.INTERNAL_SERVER_ERROR,
                        f"Cannot write {EXCEL_OUTPUT}. Close the Excel file "
                        "if it is open, and check folder permissions.")
                except OSError as exc:
                    self.log_message("Excel save failed: %r", exc)
                    return self._error(HTTPStatus.INTERNAL_SERVER_ERROR,
                        f"Cannot save Excel in {RUN_ROOT}: {exc}")
                return self._json(HTTPStatus.OK, {
                    "ok": True,
                    "saved_to": str(saved),
                    "filename": saved.name,
                    "message": "Excel file saved in run folder.",
                })
            return self._json(HTTPStatus.OK, payload)
        except (SolverError, ValueError) as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:                       # never leak a traceback
            self.log_message("solve failed: %r", exc)
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR,
                               "The solver failed on these inputs.")

    def _reject(self):
        self._json(HTTPStatus.METHOD_NOT_ALLOWED,
                   {"ok": False, "error": f"{self.command} is not supported."},
                   extra={"Allow": "GET, HEAD, POST"})

    do_PUT = do_DELETE = do_PATCH = _reject

    # -- static files --------------------------------------------------- #
    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        # Normalise first, then prove the result is still inside web/.
        clean = posixpath.normpath(path).lstrip("/")
        target = (WEB_ROOT / clean).resolve()
        try:
            target.relative_to(WEB_ROOT)
        except ValueError:
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")
        if not target.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")

        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "application/json"):
            ctype += "; charset=utf-8"
        cache = "no-cache"      # the page and its assets ship together
        self._send(HTTPStatus.OK, target.read_bytes(), ctype,
                   extra={"Cache-Control": cache})


def make_server(host="127.0.0.1", port=8501, quiet=False,
                download_exports=False) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,),
                   {"quiet": quiet, "download_exports": download_exports})
    socketserver.TCPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), handler)


def serve_in_background(host="127.0.0.1", port=0):
    """Start a server on its own thread. Returns (server, thread, base_url)."""
    httpd = make_server(host, port, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, f"http://{host}:{httpd.server_address[1]}"
