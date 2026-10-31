/* (r, Q) solver — reads /api/meta once, posts to /api/solve on every change,
   and rewrites the verdict, the derivation, both tables and the figure. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = {
    form: $("controls"), base: $("base-fields"), distName: $("dist-name"),
    distHelp: $("dist-help"), distFields: $("dist-fields"),
    singlePass: $("single-pass"), tol: $("tol"), maxIter: $("max-iter"),
    example: $("example"), loadExample: $("load-example"),
    exampleNote: $("example-note"),
    reset: $("reset"), dlCsv: $("dl-csv"), dlTxt: $("dl-txt"),
    dlXlsx: $("dl-xlsx"), excelStatus: $("excel-save-status"),
    verdictMath: $("verdict-math"), verdictLine: $("verdict-line"),
    alert: $("alert"), narrative: $("narrative"), legend: $("legend"),
    traceBody: $("trace-body"), summary: $("summary").tBodies[0],
    cost: $("cost").tBodies[0], chart: $("chart"),
    notes: $("notes"), notesSection: $("notes-section"),
    tabs: $("tabs"), indicator: $("tabs-indicator"),
    panels: $("panels"), track: $("track"), live: $("live"),
    readout: $("chart-readout"), baseUnit: $("base-unit"), steps: $("steps"),
    hMode: $("h-mode"), dMode: $("d-mode"),
    hDerive: $("h-derive-fields"), dDerive: $("d-derive-fields"),
    distBlock: $("dist-block"), derivation: $("derivation"),
    derivationBlock: $("derivation-block"),
    dDist: $("d-dist"), dDistControl: $("d-dist-control"),
    soMode: $("stockout-mode"), soHelp: $("stockout-help"),
    soFields: $("stockout-fields"), pMode: $("p-mode"), pHost: $("p-host"),
    pDerive: $("p-derive-fields"), penaltyBlock: $("penalty-block"),
    periodic: $("periodic"), periodicFields: $("periodic-fields"),
    methodGroup: $("method-group"),
    traceHead: $("trace").tHead, traceCaption: $("trace-caption"),
    stepsCaption: $("steps-caption"),
    modelAfter: $("model-after"), modelMethod: $("model-method"),
    modelP2: $("model-p2"), modelP2After: $("model-p2-after"),
    mastheadSub: $("masthead-sub"),
    p1Head: $("p1-head"), p2Block: $("p2-block"), p2Steps: $("p2-steps"),
    p2Summary: $("p2-summary").tBodies[0], p2Cost: $("p2-cost").tBodies[0],
    compare: $("compare"), comparison: $("comparison").tBodies[0],
    compareCaption: $("compare-caption"),
    verdictP2Math: $("verdict-p2-math"), verdictP2Line: $("verdict-p2-line"),
    work: document.querySelector(".core--work"),
  };

  // The page as it is written is the backorder model; these are put back
  // whenever the answer on screen is that model again.
  const B2_HTML = {
    head: el.traceHead.innerHTML,
    trace: el.traceCaption.innerHTML,
    steps: el.stepsCaption.innerHTML,
    after: el.modelAfter.innerHTML,
    method: el.modelMethod.innerHTML,
    sub: el.mastheadSub.textContent,
  };

  let meta = null;
  let last = null;
  let pending = 0;

  const SYMBOLS = [
    ["D", "demand per time unit"], ["A", "cost of one replenishment"],
    ["h", "cost of holding one unit for one time unit"],
    ["p", "penalty per unit short"], ["l", "lead time"],
    ["Q", "order quantity"], ["r", "reorder point"],
    ["G", "cdf of lead-time demand"], ["n(r)", "expected shortage per cycle"],
  ];

  /* ── numbers ──────────────────────────────────────────────────── */

  const num = (x, dp = 3) =>
    x === null || x === undefined || Number.isNaN(x)
      ? "—"
      : x.toLocaleString("en-US", { minimumFractionDigits: 3,
                                    maximumFractionDigits: 3 });

  const trim = (x, dp = 3) =>
    x === null || x === undefined
      ? "—"
      : Number(x.toFixed(3)).toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  const round = (x) => Number(x.toFixed(10));

  /* ── KaTeX, with the plain-text fallback left in place ─────────── */

  const hasKatex = () => typeof window.katex !== "undefined";

  function tex(node, source, display = true) {
    if (!hasKatex() || !node) return;
    try {
      katex.render(source, node, { displayMode: display, throwOnError: false });
    } catch (err) { /* keep the fallback */ }
  }

  /* ── the model, one spelling per stockout basis ─────────────────
     These are the model's own equations, not numbers: the numbers all come
     back from the solver. Each has its TeX and the plain spelling the page
     keeps when KaTeX is away. The backorder entry is the page as written. */

  const HOLD = String.raw`h\!\left(\tfrac{Q}{2}+r-Dl\right)+\frac{AD}{Q}`;
  const EOQ_TEX = String.raw`Q=\sqrt{\dfrac{2AD}{h}}`;
  const MODEL = {
    B2: {
      cost: [String.raw`Y(Q,r)=${HOLD}+\frac{pD\,n(r)}{Q}+Dv`,
             "Y(Q, r) = h(Q/2 + r − Dl) + AD/Q + pDn(r)/Q + Dv"],
      eq1: [String.raw`Q=\sqrt{\dfrac{2D\bigl[A+p\,n(r)\bigr]}{h}}`,
            "Q = √(2D[A + p·n(r)] / h)", "(1)"],
      eq2: [String.raw`1-G(r)=\dfrac{Qh}{pD}`, "1 − G(r) = Qh / (pD)", "(2)"],
      p2cost: [String.raw`Y_2(S)=\frac{A}{T}+h\!\left(S-DL-\tfrac{DT}{2}\right)+\frac{p\,n_{T+L}(S)}{T}+Dv`,
               "Y2(S) = A/T + h(S − DL − DT/2) + p·n(S)/T + Dv"],
      eq3: [String.raw`1-G(S)=\dfrac{hT}{p}`, "1 − G(S) = hT / p"],
      p2after: "where <em>G</em> and <em>n</em> now belong to <em>X</em><sub>T+L</sub>. Setting the derivative in <em>S</em> to zero gives",
    },
    B1: {
      cost: [String.raw`Y(Q,r)=${HOLD}+\frac{B_1 D\,\bigl[1-G(r)\bigr]}{Q}+Dv`,
             "Y(Q, r) = h(Q/2 + r − Dl) + AD/Q + B₁D[1 − G(r)]/Q + Dv"],
      eq1: [String.raw`Q=\sqrt{\dfrac{2D\bigl[A+B_1\bigl(1-G(r)\bigr)\bigr]}{h}}`,
            "Q = √(2D[A + B₁(1 − G(r))] / h)", "(1')"],
      eq2: [String.raw`g(r)=\dfrac{Qh}{B_1 D}`, "g(r) = Qh / (B₁D)", "(2')"],
      after: "where 1 − <em>G</em>(<em>r</em>) is the chance a cycle runs out, and every cycle that does costs <em>B</em><sub>1</sub> however many units it is short. Setting both partial derivatives to zero leaves two equations that have to hold together:",
      method: "Neither can be solved alone, so the method starts at the EOQ, finds the reorder point on the right tail where the density <em>g</em>(<em>r</em>) is as high as&nbsp;(2'), and returns to&nbsp;(1') for a new <em>Q</em>, until <em>r</em> stops moving. If the density never reaches that height there is no root, and <em>r</em> is held at the lowest level management allows.",
      steps: "Worked through: the formula, the numbers put into it, the result. Iteration <em>t</em> starts from <em>Q</em><sub>t</sub> (<em>Q</em><sub>0</sub> is the EOQ), reads <em>r</em><sub>t</sub> off the density in&nbsp;(2'), and ends with <em>Q</em><sub>t+1</sub> from&nbsp;(1').",
      trace: "Each iteration <em>t</em>, counted from 0. <em>Q</em><sub>t</sub> enters, equation&nbsp;(2') sets the density <em>g</em>(<em>r</em><sub>t</sub>) to <em>Q</em><sub>t</sub><em>h</em>/(<em>B</em><sub>1</sub><em>D</em>), and equation&nbsp;(1') returns <em>Q</em><sub>t+1</sub>. The answer is the last row.",
      sub: "Continuous review with a fixed cost B₁ for every cycle that runs out.",
      p2cost: [String.raw`Y_2(S)=\frac{A}{T}+h\!\left(S-DL-\tfrac{DT}{2}\right)+\frac{B_1\bigl[1-G_{T+L}(S)\bigr]}{T}+Dv`,
               "Y2(S) = A/T + h(S − DL − DT/2) + B₁[1 − G(S)]/T + Dv"],
      eq3: [String.raw`g(S)=\dfrac{hT}{B_1}`, "g(S) = hT / B₁"],
      p2after: "where <em>G</em> and <em>g</em> now belong to <em>X</em><sub>T+L</sub>. Setting the derivative in <em>S</em> to zero gives the right-tail root of",
    },
    alpha: {
      cost: [String.raw`Y(Q,r)=${HOLD}+Dv`, "Y(Q, r) = h(Q/2 + r − Dl) + AD/Q + Dv"],
      eq1: [EOQ_TEX, "Q = √(2AD / h)", "(1)"],
      eq2: [String.raw`G(r)=\alpha`, "G(r) = α", "(2)"],
      after: "with no shortage cost at all: instead the reorder point must hold the chance of running out in any one cycle to 1 − <em>α</em>. The two decisions then come apart:",
      method: "<em>Q</em> is the EOQ and <em>r</em> is the <em>α</em> quantile of lead-time demand, each read once — there is nothing to iterate. The fill rate this gives, 1 − <em>n</em>(<em>r</em>)/<em>Q</em>, is reported for information.",
      steps: "Worked through: the formula, the numbers put into it, the result. Under a cycle service level <em>Q</em> is the EOQ and <em>r</em> is read off&nbsp;(2) once.",
      trace: "One row: <em>Q</em> is the EOQ and <em>r</em> is the <em>α</em> quantile from equation&nbsp;(2), so there is nothing to iterate and <em>Q</em> leaves as it entered.",
      sub: "Continuous review at a cycle service level α: the chance a cycle does not run out.",
      p2cost: [String.raw`Y_2(S)=\frac{A}{T}+h\!\left(S-DL-\tfrac{DT}{2}\right)+Dv`,
               "Y2(S) = A/T + h(S − DL − DT/2) + Dv"],
      eq3: [String.raw`G_{T+L}(S)=\alpha`, "G(S) = α"],
      p2after: "where <em>G</em> now belongs to <em>X</em><sub>T+L</sub>. With no shortage cost, the service level sets <em>S</em>:",
    },
    beta: {
      cost: [String.raw`Y(Q,r)=${HOLD}+Dv`, "Y(Q, r) = h(Q/2 + r − Dl) + AD/Q + Dv"],
      eq1: [EOQ_TEX, "Q = √(2AD / h)", "(1)"],
      eq2: [String.raw`n(r)=(1-\beta)\,Q`, "n(r) = (1 − β)Q", "(2)"],
      after: "with no shortage cost: instead the demand expected to go unmet in a cycle may be at most the share 1 − <em>β</em> of the order. Fixing <em>Q</em> first — the sequential approach — the two decisions come apart:",
      method: "<em>Q</em> is the EOQ, and <em>r</em> is where the loss function <em>n</em>(<em>r</em>) falls to (1 − <em>β</em>)<em>Q</em>. <em>n</em> only decreases, so there is one such point, found once — nothing is iterated.",
      steps: "Worked through: the formula, the numbers put into it, the result. Under a fill rate <em>Q</em> is the EOQ and <em>r</em> solves&nbsp;(2) once.",
      trace: "One row: <em>Q</em> is the EOQ and <em>r</em> solves equation&nbsp;(2), <em>n</em>(<em>r</em>) = (1 − <em>β</em>)<em>Q</em>, so there is nothing to iterate and <em>Q</em> leaves as it entered.",
      sub: "Continuous review at a fill rate β: the share of demand met from stock.",
      p2cost: [String.raw`Y_2(S)=\frac{A}{T}+h\!\left(S-DL-\tfrac{DT}{2}\right)+Dv`,
               "Y2(S) = A/T + h(S − DL − DT/2) + Dv"],
      eq3: [String.raw`n_{T+L}(S)=(1-\beta)\,DT`, "n(S) = (1 − β)DT"],
      p2after: "where <em>n</em> now belongs to <em>X</em><sub>T+L</sub>: the shortage over a review cycle may be at most the share 1 − <em>β</em> of the demand <em>DT</em> in it. With no shortage cost, that sets <em>S</em>:",
    },
  };

  /** Typeset one equation, or leave its plain spelling (and tag) in place. */
  function setEquation(node, [source, plain, tag]) {
    if (tag) {
      if (hasKatex()) {
        node.innerHTML = '<span class="body"></span><span class="tag"></span>';
        tex(node.querySelector(".body"), source);
      } else {
        node.innerHTML = '<span class="plain"></span><span class="tag"></span>';
        node.querySelector(".plain").textContent = plain;
      }
      node.querySelector(".tag").textContent = tag;
    } else if (hasKatex()) {
      tex(node, source);
    } else {
      node.innerHTML = '<span class="plain"></span>';
      node.querySelector(".plain").textContent = plain;
    }
  }

  let shownModel = null;

  /** Rewrite section 1, the captions and the masthead for a stockout basis,
      and add Policy 2's equations when the comparison is on. */
  function renderModel(mode = "B2", periodic = false) {
    const key = `${mode}|${periodic}`;
    if (key === shownModel) return;
    shownModel = key;
    const m = MODEL[mode] || MODEL.B2;
    setEquation($("eq-cost"), m.cost);
    setEquation($("eq-1"), m.eq1);
    setEquation($("eq-2"), m.eq2);
    el.modelAfter.innerHTML = m.after || B2_HTML.after;
    el.modelMethod.innerHTML = m.method || B2_HTML.method;
    el.stepsCaption.innerHTML = m.steps
      ? `<span class="caption__label">Iteration 0</span> ${m.steps}` : B2_HTML.steps;
    el.traceCaption.innerHTML = m.trace
      ? `<span class="caption__label">Table 1</span> ${m.trace}` : B2_HTML.trace;
    const sub = m.sub || B2_HTML.sub.replace(/ Every input.*$/, "");
    el.mastheadSub.textContent = sub +
      (periodic ? " Weighed against periodic review (R, S)." : "") +
      " Every input change re-runs the whole derivation.";
    el.modelP2.hidden = !periodic;
    if (periodic) {
      setEquation($("eq-p2-cost"), m.p2cost);
      setEquation($("eq-3"), [...m.eq3, "(3)"]);
      el.modelP2After.innerHTML = m.p2after;
    }
    renderLegend(mode, periodic);
  }

  function renderStaticMath() {
    renderModel("B2", false);
  }

  /** The legend names the stockout parameter actually in the model. */
  function legendSymbols(mode, periodic) {
    const swap = {
      B1: [["B₁", "cost of a cycle that runs out"],
           ["g", "density of lead-time demand"]],
      alpha: [["α", "cycle service level"]],
      beta: [["β", "fill rate"]],
    }[mode];
    const rows = [];
    for (const row of SYMBOLS) {
      if (row[0] === "p" && swap) rows.push(...swap);
      else rows.push(row);
    }
    if (periodic)
      rows.push(["T", "review period"], ["S", "order-up-to level"],
                ["X(T+L)", "demand over the protection interval"]);
    return rows;
  }

  function renderLegend(mode = "B2", periodic = false) {
    el.legend.replaceChildren(...legendSymbols(mode, periodic).map(([sym, meaning]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = sym;
      const dd = document.createElement("dd");
      dd.textContent = meaning;
      row.append(dt, dd);
      return row;
    }));
  }

  /* ── listbox ──────────────────────────────────────────────────────
     Chromium paints a native <select> popup itself, and the row it marks as
     selected — and the one under the pointer — come from system colours that
     CSS cannot reach. In a dark theme that lands as a white strip of
     unreadable text. So the select stays as the value, and this draws the
     list. */

  const combos = new Map();

  function enhanceSelect(select) {
    if (combos.has(select)) return;
    const anchor = select.parentElement;
    anchor.classList.add("combo");
    select.classList.add("combo__native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "combo__trigger";
    trigger.id = `${select.id}-trigger`;
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", `${select.id}-list`);

    const label = document.querySelector(`label[for="${select.id}"]`);
    if (label) {
      if (!label.id) label.id = `${select.id}-label`;
      trigger.setAttribute("aria-labelledby", `${label.id} ${trigger.id}`);
    }

    const list = document.createElement("ul");
    list.className = "combo__list";
    list.id = `${select.id}-list`;
    list.setAttribute("role", "listbox");
    list.hidden = true;

    anchor.append(trigger, list);
    const combo = { select, trigger, list, open: false, active: 0 };
    combos.set(select, combo);

    trigger.addEventListener("click", () => toggleCombo(combo, !combo.open));
    trigger.addEventListener("keydown", (e) => {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        toggleCombo(combo, true);
      }
    });
    list.addEventListener("click", (e) => {
      const item = e.target.closest("[role='option']");
      if (item) commitCombo(combo, Number(item.dataset.index));
    });
    list.addEventListener("keydown", (e) => onComboKey(combo, e));
    list.addEventListener("pointermove", (e) => {
      const item = e.target.closest("[role='option']");
      if (item) setComboActive(combo, Number(item.dataset.index));
    });
    renderCombo(combo);
  }

  function renderCombo(combo) {
    const { select, trigger, list } = combo;
    const chosen = select.selectedOptions[0];
    trigger.textContent = chosen ? chosen.textContent : "";
    list.replaceChildren(...[...select.options].map((opt, i) => {
      const li = document.createElement("li");
      li.id = `${select.id}-opt-${i}`;
      li.className = "combo__option";
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(opt.selected));
      li.dataset.index = String(i);
      li.dataset.value = opt.value;
      li.textContent = opt.textContent;
      return li;
    }));
    combo.active = Math.max(0, select.selectedIndex);
  }

  function setComboActive(combo, index) {
    const items = [...combo.list.children];
    if (!items.length) return;
    combo.active = Math.max(0, Math.min(items.length - 1, index));
    items.forEach((li, i) => li.classList.toggle("is-active", i === combo.active));
    const item = items[combo.active];
    combo.list.setAttribute("aria-activedescendant", item.id);
    item.scrollIntoView({ block: "nearest" });
  }

  function toggleCombo(combo, open) {
    if (open === combo.open) return;
    combo.open = open;
    combo.list.hidden = !open;
    combo.trigger.setAttribute("aria-expanded", String(open));
    if (open) {
      setComboActive(combo, combo.select.selectedIndex);
      combo.list.tabIndex = -1;
      combo.list.focus();
    } else {
      combo.list.removeAttribute("aria-activedescendant");
      combo.trigger.focus();
    }
  }

  function commitCombo(combo, index) {
    const option = combo.select.options[index];
    if (option) {
      combo.select.value = option.value;
      renderCombo(combo);
      combo.select.dispatchEvent(new Event("input", { bubbles: true }));
      combo.select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    toggleCombo(combo, false);
  }

  function onComboKey(combo, e) {
    const last = combo.list.children.length - 1;
    const moves = { ArrowDown: combo.active + 1, ArrowUp: combo.active - 1,
                    Home: 0, End: last };
    if (e.key in moves) { e.preventDefault(); setComboActive(combo, moves[e.key]); }
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commitCombo(combo, combo.active);
    } else if (e.key === "Escape" || e.key === "Tab") {
      toggleCombo(combo, false);
    } else if (e.key.length === 1) {
      const needle = e.key.toLowerCase();
      const items = [...combo.list.children];
      const from = combo.active + 1;
      const hit = items.slice(from).concat(items.slice(0, from))
        .find((li) => li.textContent.trim().toLowerCase().startsWith(needle));
      if (hit) setComboActive(combo, Number(hit.dataset.index));
    }
  }

  function syncCombo(select) {
    const combo = combos.get(select);
    if (combo) renderCombo(combo);
  }

  document.addEventListener("pointerdown", (e) => {
    for (const combo of combos.values())
      if (combo.open && !combo.select.parentElement.contains(e.target))
        toggleCombo(combo, false);
  });

  /* ── controls ─────────────────────────────────────────────────── */

  function field(key, label, symbol, value, help, spec = {}) {
    const wrap = document.createElement("label");
    wrap.className = "field";
    const name = document.createElement("span");
    name.className = "field__label";
    name.textContent = label;
    if (symbol) {
      const sym = document.createElement("span");
      sym.className = "field__symbol";
      sym.textContent = symbol;
      name.append(" ", sym);
    }
    if (spec.per_base) {
      const per = document.createElement("span");
      per.className = "field__per";
      per.dataset.per = "base";
      name.append(per);
    }
    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.id = `f-${key}`;
    input.dataset.key = key;
    input.value = String(value);
    if (help) wrap.title = help;
    wrap.append(name, input);

    // A field may carry its own time unit: the lead time has always had one,
    // and the derived inputs need them too — a carrying charge is per year
    // while the model runs on weeks, and demand is recorded per month.
    const UNIT_IDS = { lead: "lead-unit", rate: "rate-unit", period: "period-unit",
                       review: "review-unit" };
    const UNIT_DEFAULTS = { lead: () => meta.default_lead_unit,
                            review: () => meta.default_review_unit };
    if (spec.unit && UNIT_IDS[spec.unit]) {
      wrap.classList.add("field--unit");
      const select = document.createElement("select");
      select.id = UNIT_IDS[spec.unit];
      select.name = select.id;
      fillUnits(select, spec.unitValue ||
        (UNIT_DEFAULTS[spec.unit] ? UNIT_DEFAULTS[spec.unit]() : el.baseUnit.value));
      wrap.append(select);
    }
    return wrap;
  }

  function fillUnits(select, chosen) {
    select.replaceChildren(...meta.units.map((u) => {
      const o = document.createElement("option");
      o.value = u.key;
      o.textContent = u.plural;
      return o;
    }));
    select.value = chosen;
  }

  function unitLabel(key) {
    const unit = meta.units.find((u) => u.key === key);
    return unit ? unit.label : key;
  }

  function paintUnits() {
    const base = unitLabel(el.baseUnit.value);
    document.querySelectorAll('[data-per="base"]').forEach((node) => {
      node.textContent = ` /${base}`;
    });
  }

  function buildBaseFields() {
    el.base.replaceChildren(...meta.base_fields.map((f) =>
      field(f.key, f.label, f.symbol, f.display ?? round(f.default), f.help, f)));
    // p prices the backorder basis and nothing else, so it lives with the
    // stockout picker that can make it irrelevant.
    const p = $("f-p")?.closest(".field");
    if (p) el.pHost.replaceChildren(p);
    wireLeadUnit();
    paintUnits();
  }

  function wireLeadUnit() {
    const select = $("lead-unit");
    if (select) enhanceSelect(select);
  }

  /* ── the two derivation modes ─────────────────────────────────── */

  /** Which block each mode picker drives, and what it hides when it is on. */
  const DERIVE = {
    // v is hidden alongside h: the cost function also charges D·v, and two
    // boxes for one unit cost is two numbers that can quietly disagree.
    holding: { select: () => el.hMode, host: () => el.hDerive,
               derived: "rate",
               hides: () => [$("f-h")?.closest(".field"),
                             $("f-v")?.closest(".field")] },
    demand:  { select: () => el.dMode, host: () => el.dDerive,
               derived: "period",
               hides: () => [$("f-D")?.closest(".field"), el.distBlock] },
    // p = b·v: the fraction replaces the penalty it produces.
    penalty: { select: () => el.pMode, host: () => el.pDerive,
               derived: "fraction",
               hides: () => [$("f-p")?.closest(".field")] },
  };

  function option(value, text) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = text;
    return o;
  }

  function buildModeSelects() {
    for (const [block, wiring] of Object.entries(DERIVE)) {
      const modes = meta.derive_fields[block].modes;
      wiring.select().replaceChildren(...Object.entries(modes).map(([k, m]) =>
        option(k, m.label)));
      wiring.select().value = "direct";
    }
    el.dDist.replaceChildren(...periodDists().map((n) => option(n, n)));
    el.dDist.value = periodDists()[0];
    el.soMode.replaceChildren(...Object.entries(meta.stockout_modes).map(([k, m]) =>
      option(k, m.label)));
    el.soMode.value = meta.default_stockout;
  }

  /** The laws demand per period may follow; older servers only knew Normal. */
  const periodDists = () => meta.derive_fields.demand.modes.period.dists || ["Normal"];

  /** The fields of a derive mode — per-period demand has one set per law. */
  function deriveSpecFields(block, mode) {
    const spec = meta.derive_fields[block].modes[mode];
    if (block === "demand" && spec.fields_by_dist)
      return spec.fields_by_dist[el.dDist.value] || spec.fields;
    return spec.fields;
  }

  /** Draw a block's extra inputs, and hide whatever it now supersedes. */
  function buildDeriveFields(block, values) {
    const wiring = DERIVE[block];
    const mode = wiring.select().value;
    if (block === "demand") el.dDistControl.hidden = mode !== wiring.derived;
    wiring.host().replaceChildren(...deriveSpecFields(block, mode).map((f) => {
      const given = values && f.key in values ? round(values[f.key]) : round(f.default);
      const unitValue = values &&
        (block === "holding" ? values.rate_unit : values.period_unit);
      return field(`${block}-${f.key}`, f.label, f.symbol, given, f.help,
                   { ...f, unitValue });
    }));
    for (const select of wiring.host().querySelectorAll("select"))
      enhanceSelect(select);
    // A field the derivation now supplies would otherwise sit there asking to
    // be filled in and quietly doing nothing.
    const on = mode === wiring.derived;
    for (const node of wiring.hides()) if (node) node.hidden = on;
    paintUnits();
  }

  function buildAllDeriveFields(values) {
    for (const block of Object.keys(DERIVE))
      buildDeriveFields(block, values && values[block]);
  }

  /** Switching demand to per-period: the per-period picker keeps its own law
      (Normal until it is changed — the case the lecture works, where
      variances add) and the hidden lead-time picker is brought into line
      with it, so the two never disagree. */
  function adoptPeriodDist() {
    if (!periodDists().includes(el.dDist.value)) {
      el.dDist.value = periodDists()[0];
      syncCombo(el.dDist);
    }
    followPeriodDist();
  }

  /** The lead-time picker follows the per-period law: summing periods of a law
      gives a lead-time demand of the same law, and the server refuses a
      request where the two disagree. */
  function followPeriodDist() {
    if (el.distName.value === el.dDist.value) return;
    el.distName.value = el.dDist.value;
    syncCombo(el.distName);
    buildDistFields(el.distName.value);
  }

  const stockoutMode = () => el.soMode.value || "B2";

  /** The stockout basis's own number (B₁, α or β), and what it supersedes:
      p and its derivation belong to the backorder basis only, and a service
      level has nothing to iterate, so the method controls go too. */
  function buildStockoutFields(value) {
    const mode = stockoutMode();
    const spec = meta.stockout_modes[mode];
    el.soHelp.textContent = spec.help || "";
    el.soFields.replaceChildren(...spec.fields.map((f) =>
      field(`stockout-${f.key}`, f.label, f.symbol,
            value !== undefined && value !== null ? round(value) : round(f.default),
            f.help)));
    el.penaltyBlock.hidden = mode !== "B2";
    el.methodGroup.hidden = mode === "alpha" || mode === "beta";
  }

  function buildPeriodicFields(values) {
    el.periodicFields.replaceChildren(...meta.periodic_fields.map((f) => {
      const given = values && f.key in values ? round(values[f.key]) : round(f.default);
      return field(`periodic-${f.key}`, f.label, f.symbol, given, f.help,
                   { ...f, unitValue: values && values[`${f.key}_unit`] });
    }));
    for (const select of el.periodicFields.querySelectorAll("select"))
      enhanceSelect(select);
    el.periodicFields.hidden = !el.periodic.checked;
  }

  /** The `derive` block for the request, or nothing when every mode is direct. */
  function readDerive() {
    const out = {};
    for (const [block, wiring] of Object.entries(DERIVE)) {
      const mode = wiring.select().value;
      if (mode !== wiring.derived) continue;
      // p = b·v only means anything under the backorder basis; sent under
      // another it could only fail, on a v of zero, for a number not used.
      if (block === "penalty" && stockoutMode() !== "B2") continue;
      const spec = { mode };
      for (const input of wiring.host().querySelectorAll("input"))
        spec[input.dataset.key.replace(`${block}-`, "")] = input.value;
      if (block === "holding")
        spec.rate_unit = $("rate-unit")?.value || el.baseUnit.value;
      else if (block === "demand") {
        spec.dist = el.dDist.value;
        spec.period_unit = $("period-unit")?.value || el.baseUnit.value;
      }
      out[block] = spec;
    }
    return Object.keys(out).length ? out : null;
  }

  function buildDistFields(name, values) {
    const spec = meta.distributions[name];
    el.distHelp.textContent = spec.help +
      (spec.taught ? "" : " Not in the lecture notes; included as an extension.");
    el.distFields.replaceChildren(...spec.fields.map((f) =>
      field(`dist-${f.key}`, f.label, "",
            values && f.key in values ? round(values[f.key]) : round(f.default))));
  }

  function buildSelects() {
    el.distName.replaceChildren(...Object.keys(meta.distributions).map((n) => {
      const o = document.createElement("option");
      o.value = o.textContent = n;
      return o;
    }));
    el.tol.replaceChildren(...meta.tolerances.map((t) => {
      const o = document.createElement("option");
      o.value = t.toExponential();            // one spelling for every value
      o.textContent = t === 0 ? "0 (fixed iteration count)" : t.toExponential(0).replace("e-", "e−");
      return o;
    }));
    el.tol.value = meta.default_tolerance.toExponential();
    fillUnits(el.baseUnit, meta.default_base_unit);
    el.example.replaceChildren(...[["", "Choose an example"]]
      .concat(Object.entries(meta.examples).map(([k, v]) => [k, v.label]))
      .map(([value, text]) => {
        const o = document.createElement("option");
        o.value = value;
        o.textContent = text;
        return o;
      }));
  }

  function readForm() {
    const body = { dist: { name: el.distName.value, params: {} } };
    for (const input of el.base.querySelectorAll("input"))
      body[input.dataset.key] = input.value;
    for (const input of el.distFields.querySelectorAll("input"))
      body.dist.params[input.dataset.key.replace("dist-", "")] = input.value;
    body.tol = Number(el.tol.value);
    body.max_iter = Number(el.maxIter.value);
    const mode = stockoutMode();
    // A service level reads r once; the switch is out of sight and out of play.
    body.single_pass = el.singlePass.checked && !el.methodGroup.hidden;
    body.base_unit = el.baseUnit.value;
    const leadUnit = $("lead-unit");
    body.lead_unit = leadUnit ? leadUnit.value : el.baseUnit.value;
    const derive = readDerive();
    if (derive) {
      body.derive = derive;
      // Periods of one law sum to a lead-time demand of that law, so the
      // derived law is the distribution, whatever the hidden picker says.
      if (derive.demand) body.dist.name = derive.demand.dist;
    }
    // p is sent only while it is the number in use: under another basis, or
    // when p = b·v derives it, a stray entry in the hidden box must not be
    // able to fail the request.
    if (mode === "B2" && !(derive && derive.penalty)) body.p = $("f-p")?.value;
    // The backorder basis is the request as it always was; only another basis
    // names itself, so a B2 request gets back exactly the bytes it always did.
    if (mode !== "B2")
      body.stockout = { mode, value: $("f-stockout-value")?.value };
    if (el.periodic.checked)
      body.periodic = { T: $("f-periodic-T")?.value,
                        T_unit: $("review-unit")?.value || meta.default_review_unit };
    return body;
  }

  /* ── tabs ─────────────────────────────────────────────────────── */

  const tabs = () => [...el.tabs.querySelectorAll('[role="tab"]')];
  const panels = () => [...el.track.querySelectorAll('[role="tabpanel"]')];

  /** Hold the viewport at the height of whichever section is on screen. */
  function syncHeight(animate = true) {
    const live = panels().find((p) => p.getAttribute("aria-hidden") !== "true");
    if (!live) return;
    if (!animate) el.panels.dataset.first = "1";
    el.panels.style.setProperty("--h", `${live.offsetHeight}px`);
    if (!animate) requestAnimationFrame(() => { el.panels.dataset.first = "0"; });
  }

  function moveIndicator(tab, animate = true) {
    const strip = el.tabs.getBoundingClientRect();
    const box = tab.getBoundingClientRect();
    el.indicator.dataset.first = animate ? "0" : "1";
    el.indicator.style.setProperty("--x",
      `${box.left - strip.left + el.tabs.scrollLeft}px`);
    el.indicator.style.setProperty("--w", `${box.width}px`);
    if (!animate) requestAnimationFrame(() => { el.indicator.dataset.first = "0"; });
  }

  function selectTab(tab, { focus = false, animate = true } = {}) {
    const list = tabs();
    const index = list.indexOf(tab);
    list.forEach((other, i) => {
      const on = i === index;
      other.setAttribute("aria-selected", on ? "true" : "false");
      other.tabIndex = on ? 0 : -1;
      const panel = $(other.getAttribute("aria-controls"));
      if (!panel) return;
      // The off-screen sections stay laid out so the track can slide, but they
      // are out of the accessibility tree and out of the tab order.
      panel.setAttribute("aria-hidden", on ? "false" : "true");
      if (on) panel.removeAttribute("inert");
      else panel.setAttribute("inert", "");
    });
    if (!animate) el.panels.dataset.first = "1";
    el.track.style.setProperty("--i", String(Math.max(index, 0)));
    syncHeight(animate);
    document.documentElement.style.setProperty(
      "--hue", `var(--hue-${tab.dataset.hue || 1})`);
    moveIndicator(tab, animate);
    if (focus) tab.focus();
  }

  function wireTabs() {
    el.tabs.addEventListener("click", (e) => {
      const tab = e.target.closest('[role="tab"]');
      if (tab) selectTab(tab);
    });
    el.tabs.addEventListener("keydown", (e) => {
      const list = tabs();
      const i = list.indexOf(document.activeElement);
      if (i < 0) return;
      const keys = { ArrowRight: 1, ArrowLeft: -1 };
      let next = null;
      if (e.key in keys) next = list[(i + keys[e.key] + list.length) % list.length];
      else if (e.key === "Home") next = list[0];
      else if (e.key === "End") next = list[list.length - 1];
      if (!next) return;
      e.preventDefault();
      selectTab(next, { focus: true });
    });
    window.addEventListener("resize", () => {
      const current = tabs().find((t) => t.getAttribute("aria-selected") === "true");
      if (current) moveIndicator(current, false);
      syncHeight(false);
    });

    // A solve rewrites the table and the figure, so the live section changes
    // height on its own.
    if ("ResizeObserver" in window) {
      const ro = new ResizeObserver(() => syncHeight(true));
      panels().forEach((p) => ro.observe(p));
    }
  }

  /* ── render ───────────────────────────────────────────────────── */

  function showAlert(message) {
    el.alert.textContent = message;
    el.alert.hidden = !message;
  }

  function renderVerdict(data) {
    const { answer, flags } = data;
    if (hasKatex()) {
      katex.render(
        String.raw`(Q^{*},\,r^{*})=\bigl(${trim(answer.Q)},\;${trim(answer.r)}\bigr)`,
        el.verdictMath, { displayMode: true, throwOnError: false });
    } else {
      el.verdictMath.textContent =
        `(Q*, r*) = (${trim(answer.Q)}, ${trim(answer.r)})`;
    }

    let line;
    if (flags.degenerate) {
      line = "These costs have no optimal policy — the figures above are a " +
             "fallback. The note below says why and what to change.";
    } else if (!flags.converged) {
      line = data.settings && data.settings.tolerance === 0
        ? `Completed ${data.iterations.length} iterations as requested (tol = 0: no early stopping).`
        : `The reorder point was still moving after ${data.iterations.length} iterations. Raise the iteration cap.`;
    } else if (flags.single_pass) {
      line = `Approximate: Q stays at the EOQ of ${trim(answer.eoq)} and r comes ` +
             "from equation (2) once.";
    } else {
      line = `Order ${trim(answer.Q)} units whenever inventory position falls to ` +
             `${trim(answer.r)}. That holds ${trim(answer.safety_stock)} ` +
             `units of safety stock and serves ` +
             `${(answer.fill_rate * 100).toFixed(3)}% of demand from stock.`;
    }
    el.verdictLine.textContent = line;
    el.live.textContent =
      `Q* ${trim(answer.Q)}, r* ${trim(answer.r)}. ${line}`;
  }

  function stepItem(step) {
    const li = document.createElement("li");
    li.className = "step";

    const label = document.createElement("p");
    label.className = "step__label";
    label.textContent = step.label;

    const math = document.createElement("div");
    math.className = "step__math";
    math.textContent = step.plain;            // the fallback, if KaTeX is away
    if (hasKatex()) {
      try {
        katex.render(step.tex, math, { displayMode: true, throwOnError: false });
      } catch (err) { /* keep the plain spelling */ }
    }

    li.append(label, math);
    return li;
  }

  function renderSteps(data) {
    // Whatever had to be worked out before the iteration could start sits
    // above it, in the order it was done, rather than arriving as given data.
    const derivation = data.derivation || [];
    el.derivationBlock.hidden = derivation.length === 0;
    el.derivation.replaceChildren(...derivation.map(stepItem));
    const worked = data.steps_by_iteration || [{ index: 0, steps: data.steps }];
    el.steps.replaceChildren(...worked.flatMap((item) => {
      const heading = document.createElement("li");
      heading.className = "iteration-step-heading";
      heading.textContent = `ITERATION ${item.index} — detailed calculation`;
      return [heading, ...item.steps.map(stepItem)];
    }));
  }

  /** Column heads as the solver names them for this basis; the backorder
      model keeps the heads the page was written with. */
  function renderTraceHead(data) {
    const heads = data.stockout && data.stockout.mode !== "B2"
      ? data.stockout.iteration_headers : null;
    if (!heads) {
      if (el.traceHead.dataset.mode) {
        el.traceHead.innerHTML = B2_HTML.head;
        delete el.traceHead.dataset.mode;
      }
      return;
    }
    const tr = document.createElement("tr");
    tr.append(...heads.map((text) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = "num";
      th.textContent = text;
      return th;
    }));
    el.traceHead.replaceChildren(tr);
    el.traceHead.dataset.mode = data.stockout.mode;
  }

  /** Policy 2's working and tables, and the comparison on the answer. */
  function renderPolicy2(data) {
    const p2 = data.policy2, cmp = data.comparison;
    const on = Boolean(p2 && cmp);
    el.p1Head.hidden = !on;
    el.p2Block.hidden = !on;
    el.compare.hidden = !on;
    if (!on) {
      el.p2Steps.replaceChildren();
      el.verdictP2Line.textContent = "";
      return "";
    }
    el.p2Steps.replaceChildren(...p2.steps.map(stepItem));
    listTable(el.p2Summary, p2.summary, { units: true });
    listTable(el.p2Cost, p2.cost, { totalLast: true });
    listTable(el.comparison, cmp.rows, { totalLast: true, units: true });

    const S = trim(p2.answer.S);
    if (hasKatex()) {
      katex.render(String.raw`S^{*}=${S}`, el.verdictP2Math,
                   { displayMode: true, throwOnError: false });
    } else {
      el.verdictP2Math.textContent = `S* = ${S}`;
    }
    const per = data.units.base_label;
    el.compareCaption.innerHTML = '<span class="caption__label">Table 6</span>';
    el.compareCaption.append(
      ` Policy 1 against Policy 2, per ${per}. Both pay the same D·v for the ` +
      "goods, so the choice is made without it.");

    const review = `${trim(p2.T, 4)} ${p2.T === 1 ? unitLabel(p2.T_unit) : unitPlural(p2.T_unit)}`;
    const head = `Policy 2: review every ${review} and order up to ` +
                 `${trim(p2.answer.S, 2)}, holding ${trim(p2.answer.safety_stock, 2)} ` +
                 "units of safety stock.";
    const choice = cmp.chosen === "Either"
      ? "The two policies cost the same."
      : `${cmp.chosen} is cheaper, by ${trim(cmp.difference, 4)} per ${per}.`;
    el.verdictP2Line.textContent = `${head} ${choice}`;
    return ` Policy 2: S* ${S}. ${choice}`;
  }

  function unitPlural(key) {
    const unit = meta.units.find((u) => u.key === key);
    return unit ? unit.plural : key;
  }

  function renderTrace(data) {
    renderTraceHead(data);
    el.traceBody.replaceChildren(...data.iterations.map((it, i) => {
      const tr = document.createElement("tr");
      tr.style.setProperty("--row", String(i));
      if (!data.flags.degenerate && data.flags.converged &&
          i === data.iterations.length - 1 && data.iterations.length > 1) {
        tr.className = "settled";
      }
      for (const v of [it.index, num(it.Q), num(it.tail, 6), num(it.G, 6),
                       num(it.r), num(it.n_r, 6), num(it.Q_next),
                       it.delta_r === null ? "—" : num(it.delta_r, 6)]) {
        const td = document.createElement("td");
        td.className = "num";
        td.textContent = v;
        tr.append(td);
      }
      return tr;
    }));
  }

  function listTable(target, rows, { totalLast = false, units = false } = {}) {
    target.replaceChildren(...rows.map((row, i) => {
      const { name, formula, tex, label, value, unit } = row;
      const tr = document.createElement("tr");
      tr.style.setProperty("--row", String(i));
      if (totalLast && i === rows.length - 1) tr.className = "total";

      const a = document.createElement("td");
      if (name) {
        const words = document.createElement("span");
        words.className = "row__name";
        words.textContent = name;
        a.append(words);
        if (formula) {
          const math = document.createElement("span");
          math.className = "row__tex";
          math.textContent = formula;        // readable without KaTeX
          if (tex && hasKatex()) {
            try {
              katex.render(tex, math, { displayMode: false, throwOnError: false });
            } catch (err) { /* keep the plain spelling */ }
          }
          a.append(" ", math);
        }
      } else {
        a.textContent = label;
      }
      const b = document.createElement("td");
      b.className = "figure-cell";
      b.textContent = value;
      tr.append(a, b);
      if (units) {
        const c = document.createElement("td");
        c.className = "meaning";
        c.textContent = unit || "";
        tr.append(c);
      }
      return tr;
    }));
  }

  function renderNotes(notes) {
    el.notesSection.hidden = notes.length === 0;
    el.notes.replaceChildren(...notes.map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }));
  }

  /* ── figure ───────────────────────────────────────────────────── */

  const SVG = "http://www.w3.org/2000/svg";

  function renderChart(data) {
    el.chart.replaceChildren();
    const pts = data.iterations;
    probe = null;
    el.chart.removeAttribute("data-active");
    if (pts.length < 2) {
      const p = document.createElement("p");
      p.className = "caption";
      p.textContent = "Iteration 0 only — nothing to plot.";
      el.chart.append(p);
      el.readout.replaceChildren();
      return;
    }

    const panels = [
      { key: "r", cls: "series-r", dot: "dot-r", colour: "var(--mint)",
        vals: pts.map((p) => p.r) },
      { key: "Q", cls: "series-q", dot: "dot-q", colour: "var(--violet)",
        vals: pts.map((p) => p.Q_next) },
    ];

    const W = 660, PH = 84, GAP = 36, m = { t: 14, r: 46, b: 36, l: 64 };
    const H = m.t + panels.length * PH + (panels.length - 1) * GAP + m.b;
    const iw = W - m.l - m.r;
    const x = (i) => m.l + (iw * i) / (pts.length - 1);

    const scales = [];
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.setAttribute("role", "img");
    svg.setAttribute("tabindex", "0");
    svg.setAttribute("aria-label",
      `Convergence of r and Q over ${pts.length} iterations, numbered from 0. ` +
      "Use the arrow keys to read each iteration.");

    const add = (tag, attrs, text) => {
      const node = document.createElementNS(SVG, tag);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
      if (text !== undefined) node.textContent = text;
      svg.append(node);
      return node;
    };

    panels.forEach((panel, pi) => {
      const top = m.t + pi * (PH + GAP);
      const lo = Math.min(...panel.vals), hi = Math.max(...panel.vals);
      const span = hi - lo;
      const y = (v) => span < 1e-12 ? top + PH / 2
                                    : top + PH - ((v - lo) / span) * PH;
      scales.push(y);

      add("line", { x1: m.l, x2: m.l + iw, y1: top, y2: top, class: "gridline" });
      add("line", { x1: m.l, x2: m.l + iw, y1: top + PH, y2: top + PH, class: "gridline" });
      add("line", { x1: m.l, x2: m.l, y1: top, y2: top + PH, class: "axis" });
      add("text", { x: m.l - 10, y: top + 4, "text-anchor": "end", class: "tick" },
          trim(hi, 2));
      add("text", { x: m.l - 10, y: top + PH + 4, "text-anchor": "end", class: "tick" },
          trim(lo, 2));

      const d = panel.vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("");
      const path = add("path", { d, class: `series ${panel.cls}` });
      requestAnimationFrame(() => {
        try { path.style.setProperty("--len", path.getTotalLength()); }
        catch (err) { /* no geometry in a headless DOM */ }
      });
      panel.vals.forEach((v, i) => {
        const c = add("circle", { cx: x(i), cy: y(v), r: 3, class: panel.dot });
        c.style.setProperty("--row", String(i));
      });
      add("text", { x: m.l + iw + 10, y: y(panel.vals.at(-1)) + 4,
                    class: "key", fill: panel.colour, "text-anchor": "start" },
          panel.key);
    });

    const axisY = H - m.b + 4;
    add("line", { x1: m.l, x2: m.l + iw, y1: axisY, y2: axisY, class: "axis" });
    const every = pts.length > 12 ? Math.ceil(pts.length / 10) : 1;
    pts.forEach((_, i) => {
      if (i % every !== 0 && i !== pts.length - 1) return;
      add("text", { x: x(i), y: axisY + 16, "text-anchor": "middle", class: "tick" },
          String(pts[i].index));
    });
    add("text", { x: m.l + iw / 2, y: H - 3, "text-anchor": "middle", class: "tick" },
        "iteration t");

    // the crosshair and the two markers the pointer and the keys drive
    const guide = add("line", { x1: m.l, x2: m.l, y1: m.t - 4,
                                y2: H - m.b + 4, class: "guide" });
    const markers = panels.map((panel) =>
      add("circle", { cx: m.l, cy: m.t, r: 5.5,
                      class: `marker marker-${panel.key.toLowerCase()}` }));
    const hit = add("rect", { x: 0, y: 0, width: W, height: H, class: "hit" });
    svg.append(hit);                     // keep the hit area on top

    el.chart.append(svg);

    probe = { svg, pts, x, width: W, guide, markers,
              yr: scales[0], yq: scales[1] };
    clearProbe();
    wireProbe();
  }

  /* ── solving ──────────────────────────────────────────────────── */

  /* ── reading the figure ─────────────────────────────────────── */

  let probe = null;          // { svg, pts, x, panels, guide, markers }

  function clearProbe() {
    if (!probe) return;
    el.chart.removeAttribute("data-active");
    el.readout.replaceChildren(hint());
  }

  function hint() {
    const span = document.createElement("span");
    span.className = "readout__hint";
    span.textContent =
      "Point at the figure, or focus it and use the arrow keys, to read an iteration.";
    return span;
  }

  function chip(cls, label, value) {
    const span = document.createElement("span");
    span.className = cls;
    const b = document.createElement("b");
    b.textContent = value;
    span.append(`${label} `, b);
    return span;
  }

  function showPass(i) {
    if (!probe) return;
    const n = probe.pts.length;
    const index = Math.max(0, Math.min(n - 1, i));
    const pass = probe.pts[index];
    probe.guide.setAttribute("x1", probe.x(index));
    probe.guide.setAttribute("x2", probe.x(index));
    probe.markers.forEach((m) => {
      m.setAttribute("cx", probe.x(index));
      m.setAttribute("cy", m.dataset.y
        ? Number(m.dataset.y) : 0);
    });
    probe.markers[0].setAttribute("cy", probe.yr(pass.r));
    probe.markers[1].setAttribute("cy", probe.yq(pass.Q_next));
    el.chart.dataset.active = String(index);

    el.readout.replaceChildren(
      chip("pass", "iteration", String(pass.index)),
      chip("swatch-r", `r${pass.index} =`, trim(pass.r, 4)),
      chip("swatch-q", `Q${pass.index + 1} =`, trim(pass.Q_next, 4)),
      chip("", `n(r${pass.index}) =`, trim(pass.n_r, 6)),
      chip("", "|Δr| =", pass.delta_r === null ? "—" : trim(pass.delta_r, 6)));
    probe.svg.setAttribute("aria-label",
      `Convergence over ${n} iterations, numbered from 0. Iteration ${pass.index}: ` +
      `r${pass.index} ${trim(pass.r, 4)}, Q${pass.index + 1} ${trim(pass.Q_next, 4)}.`);
  }

  function nearest(event) {
    if (!probe) return 0;
    const box = probe.svg.getBoundingClientRect();
    const scale = probe.width / (box.width || 1);
    const local = (event.clientX - box.left) * scale;
    let best = 0, bestGap = Infinity;
    probe.pts.forEach((_, i) => {
      const gap = Math.abs(probe.x(i) - local);
      if (gap < bestGap) { bestGap = gap; best = i; }
    });
    return best;
  }

  function wireProbe() {
    const { svg } = probe;
    svg.addEventListener("pointermove", (e) => showPass(nearest(e)));
    svg.addEventListener("pointerdown", (e) => showPass(nearest(e)));
    svg.addEventListener("pointerleave", clearProbe);
    svg.addEventListener("blur", clearProbe);
    svg.addEventListener("focus", () => {
      if (!el.chart.hasAttribute("data-active")) showPass(0);
    });
    svg.addEventListener("keydown", (e) => {
      const current = Number(el.chart.dataset.active ?? 0);
      const step = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: 1, ArrowDown: -1 };
      if (e.key in step) { e.preventDefault(); showPass(current + step[e.key]); }
      else if (e.key === "Home") { e.preventDefault(); showPass(0); }
      else if (e.key === "End") { e.preventDefault(); showPass(probe.pts.length - 1); }
      else if (e.key === "Escape") { svg.blur(); clearProbe(); }
    });
  }

  function replay() {
    el.work.classList.remove("animate");
    void el.work.offsetWidth;
    el.work.classList.add("animate");
  }

  async function solve() {
    // A changed input makes any earlier "saved" message outdated.
    el.excelStatus.hidden = true;
    el.excelStatus.textContent = "";
    const id = ++pending;
    let reply;
    try {
      const res = await fetch("/api/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readForm()),
      });
      reply = await res.json();
    } catch (err) {
      if (id === pending) showAlert("The server did not answer. Is it still running?");
      return;
    }
    if (id !== pending) return;

    if (!reply.ok) {
      last = null;
      showAlert(reply.error);
      setDownloads(false);
      return;
    }
    showAlert("");
    last = reply;
    renderModel(reply.stockout ? reply.stockout.mode : "B2", Boolean(reply.policy2));
    renderVerdict(reply);
    const p2live = renderPolicy2(reply);
    if (p2live) el.live.textContent += p2live;
    renderSteps(reply);
    renderTrace(reply);
    listTable(el.summary, reply.summary, { units: true });
    listTable(el.cost, reply.cost, { totalLast: true });
    // Policy 2's warnings are as much warnings as Policy 1's, so they join
    // the same list above the tabs rather than waiting behind a click.
    renderNotes([...reply.notes,
                 ...(reply.policy2 ? reply.policy2.notes.map((n) => `Policy 2: ${n}`) : []),
                 ...(reply.comparison ? reply.comparison.notes : [])]);
    renderChart(reply);
    setDownloads(true);
    replay();
    syncHeight(true);
  }

  function setDownloads(on) {
    el.dlCsv.disabled = !on;
    el.dlTxt.disabled = !on;
    el.dlXlsx.disabled = !on;
  }

  function download(text, filename, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  /* ── wiring ───────────────────────────────────────────────────── */

  let timer = null;
  const debounce = () => {
    clearTimeout(timer);
    timer = setTimeout(solve, 220);
  };

  function loadExample() {
    const key = el.example.value;
    if (!key || !meta.examples[key]) {
      showAlert("Choose an example first.");
      return;
    }
    const ex = meta.examples[key];
    const derive = ex.derive || {};
    // The homework problems state a carrying charge and demand per period, so
    // loading one switches the form into the modes it was written in — and
    // Problem 3 names its stockout basis, prices p off v, and asks for the
    // periodic-review comparison too.
    el.hMode.value = derive.holding ? "rate" : "direct";
    el.dMode.value = derive.demand ? "period" : "direct";
    el.pMode.value = derive.penalty ? "fraction" : "direct";
    el.dDist.value = (derive.demand && derive.demand.dist) || periodDists()[0];
    for (const select of [el.hMode, el.dMode, el.pMode, el.dDist]) syncCombo(select);
    const stockout = ex.stockout || { mode: meta.default_stockout };
    el.soMode.value = stockout.mode;
    syncCombo(el.soMode);
    buildStockoutFields(stockout.value);
    el.periodic.checked = Boolean(ex.periodic);
    buildPeriodicFields(ex.periodic);
    const shown = Object.fromEntries(
      meta.base_fields.filter((f) => f.display).map((f) => [f.key, f]));
    for (const [k, v] of Object.entries(ex.values)) {
      const input = $(`f-${k}`);
      if (!input) continue;
      input.value = shown[k] && Math.abs(v - shown[k].default) < 1e-12
        ? shown[k].display : String(round(v));
    }
    el.baseUnit.value = ex.base_unit;
    syncCombo(el.baseUnit);
    const leadInput = $("f-lead_time");
    if (leadInput) leadInput.value = String(round(ex.lead_value));
    const leadUnit = $("lead-unit");
    if (leadUnit) { leadUnit.value = ex.lead_unit; syncCombo(leadUnit); }
    paintUnits();
    el.distName.value = ex.distribution;
    syncCombo(el.distName);
    buildDistFields(ex.distribution, ex.params);
    buildAllDeriveFields(ex.derive);
    // What the example is meant to come out at — for the homework problems,
    // the answer worked by hand. The whole point of the exercise is comparing
    // the two, so it belongs beside the result rather than in the source.
    el.exampleNote.textContent = ex.expected || "";
    el.exampleNote.hidden = !ex.expected;
    showAlert("");
    solve();
  }

  function resetAll() {
    fillUnits(el.baseUnit, meta.default_base_unit);
    syncCombo(el.baseUnit);
    buildBaseFields();
    el.distName.value = Object.keys(meta.distributions)[0];
    syncCombo(el.distName);
    buildDistFields(el.distName.value);
    el.hMode.value = "direct";
    el.dMode.value = "direct";
    el.pMode.value = "direct";
    el.dDist.value = periodDists()[0];
    for (const select of [el.hMode, el.dMode, el.pMode, el.dDist]) syncCombo(select);
    buildAllDeriveFields(null);
    el.soMode.value = meta.default_stockout;
    syncCombo(el.soMode);
    buildStockoutFields(null);
    el.periodic.checked = false;
    buildPeriodicFields(null);
    el.singlePass.checked = false;
    el.tol.value = meta.default_tolerance.toExponential();
    syncCombo(el.tol);
    el.maxIter.value = "200";
    el.example.value = "";
    syncCombo(el.example);
    el.exampleNote.textContent = "";
    el.exampleNote.hidden = true;
    showAlert("");
    solve();
  }

  function wireReveals() {
    const targets = [...document.querySelectorAll(".reveal")];
    targets.forEach((node, i) => node.style.setProperty("--delay", `${i * 90}ms`));
    if (!("IntersectionObserver" in window)) {
      targets.forEach((n) => n.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      }
    }, { rootMargin: "0px 0px -8% 0px" });
    targets.forEach((n) => io.observe(n));
  }

  const META_KEYS = ["base_fields", "distributions", "examples", "tolerances",
                     "default_tolerance", "units", "default_base_unit",
                     "default_lead_unit", "derive_fields", "stockout_modes",
                     "default_stockout", "periodic_fields", "default_review_unit"];

  async function init() {
    try {
      meta = await (await fetch("/api/meta")).json();
    } catch (err) {
      showAlert("Could not reach the server. Start it with: python app_desktop.py --browser");
      return;
    }
    const missing = META_KEYS.filter((key) => meta[key] === undefined);
    if (missing.length) {
      // A running server keeps its old code in memory; the files on disk have
      // already moved on. Say that rather than failing somewhere deeper.
      showAlert(
        "This page is newer than the server answering it — it is missing " +
        missing.join(", ") + ". Stop the server and start it again: " +
        "python app_desktop.py --browser");
      return;
    }
    buildSelects();
    buildModeSelects();
    buildBaseFields();
    buildDistFields(el.distName.value);
    [el.baseUnit, el.distName, el.tol, el.example, el.hMode, el.dMode,
     el.dDist, el.soMode, el.pMode].forEach(enhanceSelect);
    buildAllDeriveFields(null);
    buildStockoutFields(null);
    buildPeriodicFields(null);
    renderStaticMath();
    renderLegend();
    setDownloads(false);
    wireTabs();
    wireReveals();
    selectTab(tabs()[0], { animate: false });

    el.form.addEventListener("submit", (e) => { e.preventDefault(); solve(); });
    el.form.addEventListener("input", (e) => {
      if (e.target === el.example) return;
      debounce();
    });
    el.distName.addEventListener("change", () => {
      buildDistFields(el.distName.value);
      solve();
    });
    el.baseUnit.addEventListener("change", paintUnits);
    for (const block of Object.keys(DERIVE)) {
      DERIVE[block].select().addEventListener("change", () => {
        if (block === "demand" && el.dMode.value === "period") adoptPeriodDist();
        buildDeriveFields(block, null);
        solve();
      });
    }
    el.dDist.addEventListener("change", () => {
      followPeriodDist();
      buildDeriveFields("demand", null);
      solve();
    });
    el.soMode.addEventListener("change", () => {
      buildStockoutFields(null);
      solve();
    });
    el.periodic.addEventListener("change", () => {
      el.periodicFields.hidden = !el.periodic.checked;
    });
    el.loadExample.addEventListener("click", loadExample);
    el.reset.addEventListener("click", resetAll);
    el.dlCsv.addEventListener("click", () =>
      last && download(last.csv, "rq_solution.csv", "text/csv;charset=utf-8"));
    el.dlTxt.addEventListener("click", () =>
      last && download(last.text, "rq_solution.txt", "text/plain;charset=utf-8"));
    el.dlXlsx.addEventListener("click", async () => {
      if (!last) return;
      el.dlXlsx.disabled = true;
      try {
        const response = await fetch("/api/export-xlsx", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(readForm())
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || "Cannot create Excel workbook");
        }
        // Hosted mode: the server streams the workbook back as a download.
        const ctype = response.headers.get("Content-Type") || "";
        if (ctype.includes("spreadsheetml")) {
          const blob = await response.blob();
          const link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = "rq_iteration_results.xlsx";
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(link.href), 1000);
          el.excelStatus.textContent = "Excel downloaded: rq_iteration_results.xlsx";
          el.excelStatus.hidden = false;
          showAlert("");
          return;
        }
        // Desktop mode: the Python server saves the file directly in run/.
        const result = await response.json();
        if (!result.ok || !result.saved_to) {
          throw new Error(result.error || "The server did not confirm the Excel save.");
        }
        el.excelStatus.textContent = "Saved Excel to: " + result.saved_to;
        el.excelStatus.hidden = false;
        showAlert("");
      } catch (error) {
        el.excelStatus.textContent = "Excel not saved: " + error.message;
        el.excelStatus.hidden = false;
        showAlert(error.message);
      }
      finally { el.dlXlsx.disabled = false; }
    });

    await solve();
    // fonts land after first paint and change the tab widths
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        const current = tabs().find((t) => t.getAttribute("aria-selected") === "true");
        if (current) moveIndicator(current, false);
        syncHeight(false);
      });
    }
    document.body.dataset.ready = "1";
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else
    init();
})();
