"""Self-contained HTML trace viewer: one file, no network, open it by double-clicking.

The span data is embedded as JSON with `<`, `>` and `&` escaped, and the page builds the DOM with
`textContent` only, so a model output containing `</script><script>...` can't execute.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .exporters import group_traces, summarise
from .spans import Span


def _safe_json(data: object) -> str:
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_html(spans: list[Span], title: str = "Agent trace viewer") -> str:
    traces = [
        {"summary": asdict(summarise(group)), "spans": [s.to_dict() for s in group]}
        for group in group_traces(spans).values()
    ]
    return TEMPLATE.replace("__TITLE__", title).replace("__DATA__", _safe_json(traces))


def write_html(spans: list[Span], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(spans), encoding="utf-8")
    return path


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f7f7f5; --panel: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e4e4e0;
  --agent: #5b5bd6; --step: #8e8e93; --llm: #0b84a5; --tool: #c47a00; --error: #d1343a; --sel: #eef0ff;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131316; --panel: #1c1c20; --ink: #ececf1; --muted: #9a9aa3; --line: #2c2c33;
    --agent: #8b8bf0; --step: #77777f; --llm: #3fb6d6; --tool: #f0a63a; --error: #ff6b70; --sel: #26264a;
  }
}
:root[data-theme="dark"] {
  --bg: #131316; --panel: #1c1c20; --ink: #ececf1; --muted: #9a9aa3; --line: #2c2c33;
  --agent: #8b8bf0; --step: #77777f; --llm: #3fb6d6; --tool: #f0a63a; --error: #ff6b70; --sel: #26264a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 16px; }
.tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.tabs button { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 8px;
  padding: 6px 10px; cursor: pointer; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tabs button[aria-pressed="true"] { border-color: var(--agent); box-shadow: inset 0 0 0 1px var(--agent); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 16px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.tile b { display: block; font-size: 18px; font-variant-numeric: tabular-nums; }
.tile span { color: var(--muted); font-size: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.row { display: grid; grid-template-columns: minmax(150px, 34%) 1fr 72px; gap: 8px; align-items: center;
  padding: 5px 12px; border-top: 1px solid var(--line); cursor: pointer; }
.row:first-child { border-top: 0; }
.row:hover, .row.sel { background: var(--sel); }
.name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kind { display: inline-block; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted);
  width: 38px; }
.track { position: relative; height: 14px; }
.bar { position: absolute; top: 2px; height: 10px; border-radius: 3px; min-width: 2px; }
.dur { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }
.k-agent { background: var(--agent); } .k-step { background: var(--step); } .k-llm { background: var(--llm); }
.k-tool { background: var(--tool); } .k-internal { background: var(--step); } .err { background: var(--error); }
.err-text { color: var(--error); font-weight: 600; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin: 8px 0 16px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
#detail { margin-top: 16px; padding: 14px 16px; }
#detail h2 { font-size: 15px; margin: 0 0 8px; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
td { border-top: 1px solid var(--line); padding: 5px 6px; vertical-align: top; overflow-wrap: anywhere; }
td:first-child { width: 32%; color: var(--muted); }
pre { margin: 0; white-space: pre-wrap; font: 12px/1.4 ui-monospace, Consolas, monospace; }
@media (max-width: 600px) { .row { grid-template-columns: 1fr 64px; } .track { grid-column: 1 / -1; grid-row: 2; } }
</style>
</head>
<body>
<main>
  <h1>__TITLE__</h1>
  <p class="sub">Every model and tool call as a span. Click a row for its attributes and events.</p>
  <div class="tabs" id="tabs" role="toolbar" aria-label="Traces"></div>
  <div class="tiles" id="tiles"></div>
  <div class="legend">
    <span><i class="k-agent"></i>agent</span><span><i class="k-step"></i>step</span>
    <span><i class="k-llm"></i>llm</span><span><i class="k-tool"></i>tool</span><span><i class="err"></i>error</span>
  </div>
  <div class="card" id="waterfall"></div>
  <div class="card" id="detail"><p class="sub">Select a span.</p></div>
</main>
<script type="application/json" id="trace-data">__DATA__</script>
<script>
(function () {
  const traces = JSON.parse(document.getElementById("trace-data").textContent);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text; return n; };
  const fmt = (ms) => ms >= 1000 ? (ms / 1000).toFixed(2) + " s" : Math.round(ms) + " ms";

  function tree(spans) {
    const kids = {};
    spans.forEach(s => { (kids[s.parent_id] = kids[s.parent_id] || []).push(s); });
    Object.values(kids).forEach(list => list.sort((a, b) => a.start_ms - b.start_ms));
    const out = [];
    const visit = (s, d) => { out.push([d, s]); (kids[s.span_id] || []).forEach(c => visit(c, d + 1)); };
    (kids[null] || []).forEach(r => visit(r, 0));
    return out;
  }

  function showDetail(span) {
    const box = document.getElementById("detail");
    box.replaceChildren();
    box.append(el("h2", span.status === "error" ? "err-text" : "", span.name + "  (" + fmt(span.duration_ms) + ")"));
    const table = el("table");
    const add = (k, v) => { const tr = el("tr"); tr.append(el("td", "", k));
      const td = el("td"); td.append(el("pre", "", typeof v === "string" ? v : JSON.stringify(v, null, 2)));
      tr.append(td); table.append(tr); };
    add("kind", span.kind); add("status", span.status); add("span_id", span.span_id);
    add("parent_id", span.parent_id || "(root)");
    Object.entries(span.attributes).forEach(([k, v]) => add(k, v));
    span.events.forEach(e => add("event: " + e.name, e));
    box.append(table);
  }

  function select(index) {
    const t = traces[index], s = t.summary;
    document.querySelectorAll("#tabs button").forEach((b, i) => b.setAttribute("aria-pressed", i === index));
    const tiles = document.getElementById("tiles");
    tiles.replaceChildren();
    [["total", fmt(s.total_ms)], ["llm calls", s.llm_calls + "  (" + fmt(s.llm_ms) + ")"],
     ["tool calls", s.tool_calls + "  (" + fmt(s.tool_ms) + ")"],
     ["tokens in / out", s.input_tokens + " / " + s.output_tokens], ["cost", "$" + s.cost_usd.toFixed(4)],
     ["errors", String(s.errors)]].forEach(([label, value]) => {
      const tile = el("div", "tile"); tile.append(el("b", label === "errors" && s.errors ? "err-text" : "", value),
        el("span", "", label)); tiles.append(tile); });
    const wf = document.getElementById("waterfall");
    wf.replaceChildren();
    const root = t.spans.find(x => x.parent_id === null);
    const total = Math.max(root.duration_ms, 1);
    tree(t.spans).forEach(([depth, span]) => {
      const row = el("div", "row"); row.tabIndex = 0;
      const name = el("div", "name"); name.style.paddingLeft = (depth * 14) + "px";
      name.append(el("span", "kind", span.kind), document.createTextNode(span.name));
      const track = el("div", "track");
      const bar = el("div", "bar " + (span.status === "error" ? "err" : "k-" + span.kind));
      bar.style.left = ((span.start_ms - root.start_ms) / total * 100) + "%";
      bar.style.width = (span.duration_ms / total * 100) + "%";
      bar.title = span.name + ": " + fmt(span.duration_ms);
      track.append(bar);
      row.append(name, track, el("div", "dur", fmt(span.duration_ms)));
      const pick = () => { wf.querySelectorAll(".row").forEach(r => r.classList.remove("sel"));
        row.classList.add("sel"); showDetail(span); };
      row.addEventListener("click", pick);
      row.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      wf.append(row);
    });
    document.getElementById("detail").replaceChildren(el("p", "sub", "Select a span."));
  }

  const tabs = document.getElementById("tabs");
  traces.forEach((t, i) => { const b = el("button", "", (i + 1) + ". " + t.summary.name);
    b.addEventListener("click", () => select(i)); tabs.append(b); });
  if (traces.length) select(0);
})();
</script>
</body>
</html>
"""
