"""Builds the student's downloadable copy of their work: one self-contained
HTML file that re-runs their Python in the browser (Pyodide from CDN),
lets them edit it, and shows the prediction questions with their answers.

Reuses the in-browser grading harness verbatim
(client/src/pyodide/harness.py) and the same per-question data the
"review a past question" view already assembles
(serializers.build_group_work).
"""

import html
import json
import os

from flask import Response

from server.config import REPO_ROOT
from server.models.worksheet import Question
from server.services import serializers

_HARNESS_PATH = os.path.join(REPO_ROOT, "client", "src", "pyodide", "harness.py")
_PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js"
_MARKED_CDN = "https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"


def _harness_source():
    with open(_HARNESS_PATH) as f:
        return f.read()


def _enrich_prediction(question, group_id, pred_public):
    """The student has finished the discussion and is downloading their own
    work, so it's fine to include the expected output here (unlike the live
    /state payload, which withholds it)."""
    if not pred_public:
        return None
    cfg = serializers.question_prediction_config(question) or {}
    out = dict(pred_public)
    if cfg.get("mode") == "written":
        out["prompt"] = cfg.get("prompt", "")
    else:
        item = serializers.group_prediction_item(question, group_id)
        if item:
            out["item"] = {"code": item["code"], "expected": item.get("expected", "")}
    return out


def render_export(worksheet, group, participant_key):
    work = serializers.build_group_work(group, worksheet.id, participant_key)
    questions = []
    for q in work["questions"]:
        question = Question.query.get(q["question_id"])
        q = dict(q)
        q["prediction"] = _enrich_prediction(question, group.id, q.get("prediction"))
        questions.append(q)
    payload = {
        "worksheet_title": work["worksheet_title"],
        "group_name": group.name,
        "questions": questions,
    }
    doc = _PAGE.format(
        title=html.escape(f"{worksheet.title} — your work"),
        data_json=json.dumps(payload).replace("</", "<\\/"),
        harness=_harness_source().replace("</", "<\\/"),
        pyodide_cdn=_PYODIDE_CDN,
        marked_cdn=_MARKED_CDN,
    )
    return Response(
        doc,
        mimetype="text/html",
        headers={"Content-Disposition": f'attachment; filename="{worksheet.slug}.html"'},
    )


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#fbfbfa; --fg:#1a1a1a; --muted:#666;
           --border:#ddd; --panel:#fff; --accent:#2563eb; --ok:#16a34a; --bad:#dc2626; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#1a1a1a; --fg:#eee; --muted:#999; --border:#333; --panel:#242424; --accent:#60a5fa; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
          font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width: 820px; margin: 0 auto; padding: 24px 16px 80px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  .banner {{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
             padding:10px 14px; font-size:13px; color:var(--muted); margin:14px 0 28px; }}
  .q {{ border:1px solid var(--border); border-radius:10px; background:var(--panel);
        padding:16px 18px; margin:18px 0; }}
  .q h2 {{ font-size:1.05rem; margin:0 0 10px; }}
  .prompt :is(pre,code) {{ background:rgba(127,127,127,.12); border-radius:4px; }}
  .prompt pre {{ padding:10px; overflow:auto; }}
  textarea {{ width:100%; min-height:150px; font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
              padding:10px; border:1px solid var(--border); border-radius:8px;
              background:var(--bg); color:var(--fg); resize:vertical; }}
  button {{ font:inherit; padding:7px 14px; border:0; border-radius:8px; background:var(--accent);
            color:#fff; cursor:pointer; margin-top:8px; }}
  button:disabled {{ opacity:.5; cursor:default; }}
  .results {{ margin-top:10px; font-size:13px; white-space:pre-wrap; }}
  .case {{ padding:2px 0; }}
  .case.pass::before {{ content:"\\2713 "; color:var(--ok); }}
  .case.fail::before {{ content:"\\2717 "; color:var(--bad); }}
  .meta {{ font-size:12px; color:var(--muted); margin:6px 0; }}
  .answer {{ background:rgba(127,127,127,.1); border-radius:6px; padding:8px 10px; font-size:13px; }}
  .badge {{ font-size:11px; padding:2px 7px; border-radius:99px; background:rgba(127,127,127,.15); }}
  .badge.ok {{ color:var(--ok); }} .badge.bad {{ color:var(--bad); }}
</style>
</head>
<body>
<main>
  <h1 id="wtitle"></h1>
  <div class="meta" id="gname"></div>
  <div class="banner">Offline copy of your discussion work. Running code needs an internet
  connection the first time (it downloads Python, then it's cached). Editing and reading
  everything else works offline.</div>
  <div id="questions"></div>
</main>

<script type="application/json" id="data">{data_json}</script>
<script type="text/x-python" id="harness">{harness}</script>
<script src="{marked_cdn}"></script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const HARNESS = document.getElementById('harness').textContent;
document.getElementById('wtitle').textContent = DATA.worksheet_title;
document.getElementById('gname').textContent = DATA.group_name || '';

let pyReady = null;
function loadPy() {{
  if (pyReady) return pyReady;
  pyReady = (async () => {{
    const s = document.createElement('script');
    s.src = "{pyodide_cdn}";
    const done = new Promise((res, rej) => {{ s.onload = res; s.onerror = rej; }});
    document.head.appendChild(s);
    await done;
    const py = await loadPyodide();
    await py.runPythonAsync(HARNESS);
    return py;
  }})();
  return pyReady;
}}

async function run(q, code, out, btn) {{
  btn.disabled = true;
  out.textContent = 'Loading Python…';
  try {{
    const py = await loadPy();
    const grade = py.globals.get('grade');
    const res = grade(q.setup_code || '', code, q.test_code || '', q.grading_mode === 'discussion' ? 'doctest' : (q.grading_mode || 'doctest')).toJs({{ dict_converter: Object.fromEntries }});
    grade.destroy();
    out.innerHTML = '';
    if (res.error) {{
      out.textContent = res.error;
    }} else {{
      const head = document.createElement('div');
      head.className = 'meta';
      head.textContent = res.passed_count + ' / ' + res.total_count + ' tests passing';
      out.appendChild(head);
      (res.test_results || []).forEach(t => {{
        const d = document.createElement('div');
        d.className = 'case ' + (t.passed ? 'pass' : 'fail');
        d.textContent = t.name + (t.message ? ' — ' + t.message : '');
        out.appendChild(d);
      }});
      if (res.student_output) {{
        const pre = document.createElement('pre');
        pre.textContent = res.student_output;
        out.appendChild(pre);
      }}
    }}
  }} catch (e) {{
    out.textContent = 'Error: ' + (e && e.message || e);
  }} finally {{
    btn.disabled = false;
  }}
}}

const root = document.getElementById('questions');
DATA.questions.forEach((q, i) => {{
  const el = document.createElement('section');
  el.className = 'q';
  const h = document.createElement('h2');
  h.textContent = (i + 1) + '. ' + q.title;
  el.appendChild(h);

  const prompt = document.createElement('div');
  prompt.className = 'prompt';
  prompt.innerHTML = window.marked ? marked.parse(q.prompt || '') : (q.prompt || '');
  el.appendChild(prompt);

  const isCoding = (q.problem_type || 'coding') === 'coding';
  if (isCoding && q.grading_mode !== 'discussion') {{
    const ta = document.createElement('textarea');
    ta.value = q.code || q.starter_code || '';
    el.appendChild(ta);
    const btn = document.createElement('button');
    btn.textContent = 'Run tests';
    const out = document.createElement('div');
    out.className = 'results';
    btn.onclick = () => run(q, ta.value, out, btn);
    el.appendChild(btn);
    el.appendChild(out);
  }} else if (!isCoding) {{
    const a = document.createElement('div');
    a.className = 'answer';
    a.textContent = 'Your answer: ' + JSON.stringify(q.group_response);
    if (q.group_response_correct === true) a.innerHTML += ' <span class="badge ok">correct</span>';
    if (q.group_response_correct === false) a.innerHTML += ' <span class="badge bad">not correct</span>';
    el.appendChild(a);
  }}

  if (q.prediction) {{
    const p = document.createElement('div');
    p.className = 'answer';
    p.style.marginTop = '10px';
    const pr = q.prediction;
    const esc = (s) => String(s ?? '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
    let h = '<strong>Prediction</strong><br>';
    if (pr.mode === 'written') {{
      if (pr.prompt) h += '<em>' + esc(pr.prompt) + '</em><br>';
      h += 'Your answer: ' + esc(pr.group_answer ?? '—');
    }} else {{
      if (pr.item) h += 'Call: <code>' + esc(pr.item.code) + '</code><br>';
      h += 'Your answer: <code>' + esc(pr.group_answer ?? '—') + '</code><br>';
      if (pr.item && pr.item.expected !== undefined)
        h += 'Expected: <code>' + esc(pr.item.expected) + '</code>';
      if (pr.group_correct === true) h += ' <span class="badge ok">correct</span>';
      if (pr.group_correct === false) h += ' <span class="badge bad">not correct</span>';
    }}
    p.innerHTML = h;
    el.appendChild(p);
  }}
  root.appendChild(el);
}});
</script>
</body>
</html>
"""
