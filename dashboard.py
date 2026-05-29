"""
ASBL QA Agent — Dashboard

Run:  python3 dashboard.py
Open: http://localhost:5050
"""

import os, sys, re
from datetime import datetime
import pymongo
from flask import Flask, render_template_string, request

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
from db import get_db

MONGO_URI_PROD = os.getenv("MONGO_URI_PROD")
app = Flask(__name__)

PAGE_SIZE = 25

STYLE = """
:root {
  --dark-blue:#1A376C; --mid-blue:#1F5C99; --orange:#E86C1E;
  --light-bg:#F7F9FC;  --border:#DDE3ED;   --text:#1A1A2E;
  --muted:#5A6070;     --white:#fff;
  --green:#1a7a45;     --red:#c0392b;       --yellow:#d68910;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:var(--light-bg);color:var(--text)}

.topbar{background:var(--dark-blue);color:#fff;padding:14px 32px;
        display:flex;align-items:center}
.topbar h1{font-size:1.15rem;font-weight:600}
.topbar .sub{font-size:.8rem;opacity:.65;margin-left:auto}

.container{max-width:1360px;margin:0 auto;padding:28px 24px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:28px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:28px}

.card{background:#fff;border-radius:10px;border:1px solid var(--border);padding:20px 24px}
.card h2{font-size:.73rem;text-transform:uppercase;letter-spacing:.08em;
         color:var(--muted);margin-bottom:12px}

.health-score{font-size:2.8rem;font-weight:700;line-height:1}
.health-detail{font-size:.82rem;color:var(--muted);margin-top:6px}
.sc{color:var(--red)}
.sw{color:var(--yellow)}
.sg{color:var(--green)}

.section-title{font-size:1rem;font-weight:600;color:var(--dark-blue);
               margin-bottom:14px;padding-bottom:8px;
               border-bottom:2px solid var(--orange);display:inline-block}

table{width:100%;border-collapse:collapse;font-size:.855rem}
th{text-align:left;padding:8px 12px;background:var(--light-bg);
   color:var(--muted);font-size:.73rem;text-transform:uppercase;
   letter-spacing:.06em;border-bottom:1px solid var(--border)}
td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}
tr:last-child td{border-bottom:none}
tr:hover>td{background:#f0f4fa}

.badge{display:inline-block;padding:2px 8px;border-radius:4px;
       font-size:.72rem;font-weight:600;letter-spacing:.04em}
.badge-pass   {background:#d4edda;color:#155724}
.badge-fail   {background:#f8d7da;color:#721c24}
.badge-skipped{background:#e2e3e5;color:#383d41}
.badge-high   {background:#f8d7da;color:#721c24}
.badge-medium {background:#fff3cd;color:#856404}
.badge-low    {background:#d4edda;color:#155724}

.chip{display:inline-block;padding:2px 7px;border-radius:3px;font-size:.68rem;
      background:#eef1f7;color:var(--mid-blue);margin:1px 2px;white-space:nowrap}
.chip-high{background:#fde8e8;color:var(--red)}

details{margin-top:6px}
details summary{cursor:pointer;font-size:.75rem;color:var(--mid-blue);
                font-weight:600;list-style:none;user-select:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▶ ";font-size:.65rem}
details[open] summary::before{content:"▼ "}
.convo-block{margin-top:8px;background:#f8fafc;border:1px solid var(--border);
             border-radius:6px;padding:10px 14px;font-size:.8rem;
             max-height:320px;overflow-y:auto}
.turn{margin-bottom:6px;line-height:1.45}
.turn-user{color:#1A376C;font-weight:600}
.turn-bot {color:#444}
.turn-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
            margin-right:6px;opacity:.7}
.issue-detail{font-size:.78rem;color:var(--muted);margin-top:3px;
              padding-left:8px;border-left:2px solid #f8d7da}

.fix-card{border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:12px}
.fix-card h4{font-size:.9rem;color:var(--dark-blue);margin-bottom:6px}
.fix-where{font-size:.78rem;color:var(--muted)}
.fix-outcome{font-size:.78rem;color:var(--green);margin-top:4px}
.empty{color:var(--muted);font-size:.85rem;font-style:italic;padding:12px 0}
.refresh{font-size:.75rem;color:var(--muted);text-align:right;margin-bottom:20px}

/* Filters */
.filters{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.filters input[type=date],.filters select,.filters button{
  padding:6px 10px;border:1px solid var(--border);border-radius:6px;
  font-size:.8rem;background:#fff;color:var(--text);cursor:pointer}
.filters button{background:var(--dark-blue);color:#fff;border-color:var(--dark-blue);font-weight:600}
.filters button.secondary{background:#fff;color:var(--dark-blue)}
.filters label{font-size:.78rem;color:var(--muted);font-weight:600}

/* Pagination */
.pagination{display:flex;align-items:center;gap:6px;margin-top:16px;justify-content:center}
.pagination a{padding:5px 11px;border-radius:5px;border:1px solid var(--border);
              font-size:.8rem;color:var(--mid-blue);text-decoration:none;background:#fff}
.pagination a:hover{background:var(--light-bg)}
.pagination a.active{background:var(--dark-blue);color:#fff;border-color:var(--dark-blue)}
.pagination .info{font-size:.78rem;color:var(--muted);margin:0 8px}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>ASBL QA Dashboard</title>
<style>{{ style }}</style>
</head>
<body>

<div class="topbar">
  <h1>ASBL QA Agent — Live Dashboard</h1>
  <div class="sub">{{ now }} &nbsp;·&nbsp; <a href="/" style="color:#99bbdd">Refresh</a></div>
</div>

<div class="container">
<p class="refresh">Reads live from MongoDB · reload to refresh</p>

<!-- HEALTH -->
<div class="grid-3">
{% for h in health %}
<div class="card">
  <h2>{{ h.component|title }} Health</h2>
  <div class="health-score {{ h.css }}">{{ h.score }}</div>
  <div class="health-detail">
    Fail rate: {{ h.fail_pct }}%
    &nbsp;·&nbsp; {{ h.total }} evaluated
  </div>
  <div style="font-size:.7rem;color:var(--muted);margin-top:6px">Last updated: {{ h.updated }}</div>
</div>
{% endfor %}
</div>

<!-- ANALYTICS FLAGS -->
<div class="card" style="margin-bottom:28px">
  <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:14px">
    <span class="section-title" style="margin-bottom:0">Analytics Flags</span>
    <span style="font-size:.72rem;color:var(--muted)">Last run: {{ an_updated }}</span>
  </div>
  {% if flags %}
  <table style="margin-top:0">
    <thead><tr><th>Severity</th><th>Source</th><th>Type</th><th>Detail</th></tr></thead>
    <tbody>
    {% for f in flags %}
    <tr>
      <td><span class="badge badge-{{ f.severity|lower }}">{{ f.severity }}</span></td>
      <td style="font-size:.78rem;color:var(--muted)">{{ f.source }}</td>
      <td style="font-size:.82rem;font-weight:600">{{ f.type }}</td>
      <td style="font-size:.82rem">{{ f.detail }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">No analytics flags yet.</p>
  {% endif %}
</div>

<!-- PROBLEMS + FIXES -->
<div class="grid-2">
<div class="card">
  <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:14px">
    <span class="section-title" style="margin-bottom:0">Problems Found (Feedback Agent)</span>
    <span style="font-size:.72rem;color:var(--muted)">Last calculated: {{ fb_updated }}</span>
  </div>
  {% if problems %}
  {% for p in problems %}
  <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid var(--border)">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <span class="badge badge-{{ p.urgency|lower }}">{{ p.urgency }}</span>
      <strong style="font-size:.87rem">{{ p.title }}</strong>
    </div>
    <div style="font-size:.8rem;color:var(--muted)">{{ p.what_is_wrong }}</div>
    {% if p.what_is_not_wrong %}
    <div style="font-size:.75rem;color:#888;margin-top:3px">✗ NOT: {{ p.what_is_not_wrong }}</div>
    {% endif %}
    {% if p.evidence %}
    <div style="margin-top:5px">
      {% for e in p.evidence %}
      <div style="font-size:.75rem;color:var(--muted);padding-left:10px">• {{ e }}</div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
  {% endfor %}
  {% else %}
  <p class="empty">No problems found yet.</p>
  {% endif %}
</div>

<div class="card">
  <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:14px">
    <span class="section-title" style="margin-bottom:0">Recommended Fixes (Recommendation Agent)</span>
    <span style="font-size:.72rem;color:var(--muted)">Last generated: {{ rec_updated }}</span>
  </div>
  {% if fixes %}
  {% for f in fixes %}
  <div class="fix-card">
    <h4>[{{ f.rank }}] {{ f.problem }}</h4>
    <div style="font-size:.84rem;margin-bottom:6px">{{ f.fix }}</div>
    <div class="fix-where">📁 {{ f.where }}</div>
    <div class="fix-outcome">→ {{ f.outcome }}</div>
  </div>
  {% endfor %}
  {% else %}
  <p class="empty">No recommendations yet.</p>
  {% endif %}
</div>
</div>

<!-- CHATBOT QA -->
<div class="card" style="margin-bottom:28px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:8px">
    <div>
      <span class="section-title">Chatbot QA — Results</span>
      <span style="font-size:.75rem;font-weight:400;color:var(--muted);margin-left:10px">
        {{ cb_total }} total &nbsp;·&nbsp; {{ cb_fail }} failed &nbsp;·&nbsp; {{ cb_pass }} passed
        &nbsp;·&nbsp; <span style="font-size:.7rem">Last evaluated: {{ cb_latest_at }}</span>
      </span>
    </div>
  </div>

  <!-- Filters -->
  <form method="get" action="/" style="margin-bottom:0">
    <div class="filters">
      <label>From</label>
      <input type="date" name="cb_from" value="{{ cb_from }}">
      <label>To</label>
      <input type="date" name="cb_to" value="{{ cb_to }}">
      <label>Sort</label>
      <select name="cb_sort">
        <option value="desc" {% if cb_sort=='desc' %}selected{% endif %}>Newest first</option>
        <option value="asc"  {% if cb_sort=='asc'  %}selected{% endif %}>Oldest first</option>
      </select>
      <label>Status</label>
      <select name="cb_status">
        <option value=""     {% if cb_status==''     %}selected{% endif %}>All</option>
        <option value="FAIL" {% if cb_status=='FAIL' %}selected{% endif %}>FAIL only</option>
        <option value="PASS" {% if cb_status=='PASS' %}selected{% endif %}>PASS only</option>
      </select>
      <button type="submit">Apply</button>
      <a href="/" class="secondary" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:.8rem;text-decoration:none;color:var(--dark-blue)">Reset</a>
      <!-- preserve voice page -->
      <input type="hidden" name="vc_page" value="{{ vc_page }}">
    </div>
    <!-- Chatbot page as hidden so filter submit resets to page 1 -->
    <input type="hidden" name="cb_page" value="1">
  </form>

  {% if chatbot_rows %}
  <table>
    <thead><tr>
      <th>#</th><th>Status</th><th>Score</th><th>ID</th>
      <th>Issues</th><th>Summary + Conversation</th><th>Evaluated At</th>
    </tr></thead>
    <tbody>
    {% for r in chatbot_rows %}
    <tr>
      <td style="font-size:.78rem;color:var(--muted);font-weight:600">{{ cb_offset + loop.index }}</td>
      <td><span class="badge badge-{{ r.status|lower }}">{{ r.status }}</span></td>
      <td style="font-weight:600">{{ r.score }}/10</td>
      <td style="font-family:monospace;font-size:.75rem;color:var(--muted)">{{ r.conversation_id[:26] }}</td>
      <td>
        {% for issue in r.issues %}
        <span class="chip {% if issue.severity == 'HIGH' %}chip-high{% endif %}">{{ issue.type }}</span>
        {% endfor %}
        {% for issue in r.issues %}
        {% if issue.detail %}
        <div class="issue-detail">{{ issue.detail[:120] }}</div>
        {% endif %}
        {% endfor %}
      </td>
      <td>
        <div style="font-size:.82rem;color:var(--muted)">{{ r.summary }}</div>
        {% if r.turns %}
        <details>
          <summary>Show conversation ({{ r.turns|length }} turns)</summary>
          <div class="convo-block">
            {% for turn in r.turns %}
            <div class="turn">
              <span class="turn-label turn-user">User</span>
              <span class="turn-user">{{ turn.user }}</span>
            </div>
            <div class="turn" style="margin-bottom:10px">
              <span class="turn-label turn-bot">Bot</span>
              <span class="turn-bot">{{ turn.bot }}</span>
            </div>
            {% endfor %}
          </div>
        </details>
        {% endif %}
      </td>
      <td style="font-size:.73rem;color:var(--muted);white-space:nowrap">{{ r.evaluated_at }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <!-- Chatbot Pagination -->
  <div class="pagination">
    <span class="info">Page {{ cb_page }} of {{ cb_pages }} &nbsp;·&nbsp; {{ cb_filtered }} results</span>
    {% if cb_page > 1 %}
    <a href="/?cb_page={{ cb_page-1 }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}&vc_page={{ vc_page }}">‹ Prev</a>
    {% endif %}
    {% for p in cb_page_range %}
    <a href="/?cb_page={{ p }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}&vc_page={{ vc_page }}"
       class="{% if p == cb_page %}active{% endif %}">{{ p }}</a>
    {% endfor %}
    {% if cb_page < cb_pages %}
    <a href="/?cb_page={{ cb_page+1 }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}&vc_page={{ vc_page }}">Next ›</a>
    {% endif %}
  </div>

  {% else %}
  <p class="empty">No chatbot QA results for this filter.</p>
  {% endif %}
</div>

<!-- VOICE QA -->
<div class="card" style="margin-bottom:28px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:8px">
    <div>
      <span class="section-title">Voice QA — Results</span>
      <span style="font-size:.75rem;font-weight:400;color:var(--muted);margin-left:10px">
        {{ vc_total }} total &nbsp;·&nbsp; {{ vc_fail }} failed &nbsp;·&nbsp; {{ vc_pass }} passed
        &nbsp;·&nbsp; <span style="font-size:.7rem">Last evaluated: {{ vc_latest_at }}</span>
      </span>
    </div>
  </div>

  {% if voice_rows %}
  <table>
    <thead><tr>
      <th>#</th><th>Status</th><th>Score</th><th>Call SID</th><th>Lang</th>
      <th>Issues</th><th>Summary + Transcript</th><th>Evaluated At</th>
    </tr></thead>
    <tbody>
    {% for r in voice_rows %}
    <tr>
      <td style="font-size:.78rem;color:var(--muted);font-weight:600">{{ vc_offset + loop.index }}</td>
      <td><span class="badge badge-{{ r.status|lower }}">{{ r.status }}</span></td>
      <td style="font-weight:600">{{ r.score }}/10</td>
      <td style="font-family:monospace;font-size:.75rem;color:var(--muted)">{{ r.call_sid[:26] }}</td>
      <td style="font-size:.78rem">{{ r.language }}</td>
      <td>
        {% for issue in r.issues %}
        <span class="chip {% if issue.severity == 'HIGH' %}chip-high{% endif %}">{{ issue.type }}</span>
        {% endfor %}
        {% for issue in r.issues %}
        {% if issue.detail %}
        <div class="issue-detail">{{ issue.detail[:120] }}</div>
        {% endif %}
        {% endfor %}
      </td>
      <td>
        <div style="font-size:.82rem;color:var(--muted)">{{ r.summary }}</div>
        {% if r.turns %}
        <details>
          <summary>Show transcript ({{ r.turns|length }} turns)</summary>
          <div class="convo-block">
            {% for turn in r.turns %}
            <div class="turn" style="margin-bottom:8px">
              <span class="turn-label" style="color:{% if turn.is_bot %}var(--orange){% else %}var(--mid-blue){% endif %}">
                {{ turn.speaker }}</span>
              {{ turn.text }}
            </div>
            {% endfor %}
          </div>
        </details>
        {% endif %}
      </td>
      <td style="font-size:.73rem;color:var(--muted);white-space:nowrap">{{ r.evaluated_at }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <!-- Voice Pagination -->
  <div class="pagination">
    <span class="info">Page {{ vc_page }} of {{ vc_pages }} &nbsp;·&nbsp; {{ vc_total }} results</span>
    {% if vc_page > 1 %}
    <a href="/?vc_page={{ vc_page-1 }}&cb_page={{ cb_page }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}">‹ Prev</a>
    {% endif %}
    {% for p in vc_page_range %}
    <a href="/?vc_page={{ p }}&cb_page={{ cb_page }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}"
       class="{% if p == vc_page %}active{% endif %}">{{ p }}</a>
    {% endfor %}
    {% if vc_page < vc_pages %}
    <a href="/?vc_page={{ vc_page+1 }}&cb_page={{ cb_page }}&cb_from={{ cb_from }}&cb_to={{ cb_to }}&cb_sort={{ cb_sort }}&cb_status={{ cb_status }}">Next ›</a>
    {% endif %}
  </div>

  {% else %}
  <p class="empty">No voice QA results yet.</p>
  {% endif %}
</div>

</div><!-- /container -->
</body>
</html>"""


def score_css(score):
    if score is None: return "sw"
    if score >= 7.0:  return "sg"
    if score >= 5.0:  return "sw"
    return "sc"


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()


def page_range(current, total, window=5):
    half = window // 2
    start = max(1, current - half)
    end   = min(total, start + window - 1)
    start = max(1, end - window + 1)
    return list(range(start, end + 1))


@app.route("/")
def dashboard():
    db   = get_db()
    prod = pymongo.MongoClient(MONGO_URI_PROD)
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Query params ─────────────────────────────────────────────────────
    cb_page   = max(1, int(request.args.get("cb_page",   1)))
    vc_page   = max(1, int(request.args.get("vc_page",   1)))
    cb_from   = request.args.get("cb_from",   "")
    cb_to     = request.args.get("cb_to",     "")
    cb_sort   = request.args.get("cb_sort",   "desc")
    cb_status = request.args.get("cb_status", "")

    # ── Health — calculated LIVE from actual data ─────────────────────────
    health = []

    cb_total_all = db["chatbot_qa"].count_documents({"status": {"$ne": "SKIPPED"}})
    cb_fail_all  = db["chatbot_qa"].count_documents({"status": "FAIL"})
    cb_score     = round((1 - cb_fail_all / cb_total_all) * 10, 1) if cb_total_all else None
    cb_latest    = db["chatbot_qa"].find_one({"status": {"$ne": "SKIPPED"}}, sort=[("evaluated_at", -1)])
    cb_updated   = (cb_latest.get("evaluated_at", "")[:16].replace("T", " ")) if cb_latest else "–"
    health.append({
        "component": "chatbot",
        "score":     cb_score if cb_score is not None else "–",
        "css":       score_css(cb_score),
        "fail_pct":  round(cb_fail_all / cb_total_all * 100) if cb_total_all else 0,
        "total":     cb_total_all,
        "updated":   cb_updated,
    })

    vc_total_all = db["voice_qa"].count_documents({"status": {"$ne": "SKIPPED"}})
    vc_fail_all  = db["voice_qa"].count_documents({"status": "FAIL"})
    vc_score     = round((1 - vc_fail_all / vc_total_all) * 10, 1) if vc_total_all else None
    vc_latest    = db["voice_qa"].find_one({"status": {"$ne": "SKIPPED"}}, sort=[("evaluated_at", -1)])
    vc_updated   = (vc_latest.get("evaluated_at", "")[:16].replace("T", " ")) if vc_latest else "–"
    health.append({
        "component": "voice",
        "score":     vc_score if vc_score is not None else "–",
        "css":       score_css(vc_score),
        "fail_pct":  round(vc_fail_all / vc_total_all * 100) if vc_total_all else 0,
        "total":     vc_total_all,
        "updated":   vc_updated,
    })

    # Analytics health from latest analytics run
    an_run     = db["analytics_runs"].find_one(sort=[("run_at", -1)])
    an_flags   = an_run.get("flags", []) if an_run else []
    high_flags = sum(1 for f in an_flags if f.get("severity") == "HIGH")
    an_score   = max(0.0, round(10 - high_flags * 1.5, 1)) if an_run else None
    an_updated = (an_run.get("run_at", "")[:16].replace("T", " ")) if an_run else "–"
    health.append({
        "component": "analytics",
        "score":     an_score if an_score is not None else "–",
        "css":       score_css(an_score),
        "fail_pct":  round(high_flags / max(len(an_flags), 1) * 100) if an_flags else 0,
        "total":     f"{len(an_flags)} flags",
        "updated":   an_updated,
    })

    # ── Analytics flags ───────────────────────────────────────────────────
    flags = []
    if an_run:
        for f in sorted(an_flags,
                        key=lambda x: {"HIGH":0,"MEDIUM":1,"LOW":2}.get(x.get("severity"),3)):
            flags.append({
                "severity": f.get("severity", "?"),
                "source":   f.get("source", "orchestrator"),
                "type":     f.get("type", "?"),
                "detail":   f.get("detail", ""),
            })

    # ── Problems ──────────────────────────────────────────────────────────
    fb_doc     = db["feedback"].find_one({"source": "automated"}, sort=[("submitted_at", -1)])
    fb_updated = (fb_doc.get("submitted_at", "")[:16].replace("T", " ")) if fb_doc else "–"
    problems   = []
    if fb_doc:
        for p in sorted(fb_doc.get("problems", []),
                        key=lambda x: {"HIGH":0,"MEDIUM":1,"LOW":2}.get(x.get("urgency"),3)):
            problems.append({
                "urgency":           p.get("urgency", "MEDIUM"),
                "title":             p.get("title", ""),
                "what_is_wrong":     p.get("what_is_wrong", ""),
                "what_is_not_wrong": p.get("what_is_not_wrong", ""),
                "evidence":          p.get("evidence", [])[:3],
            })

    # ── Fixes ─────────────────────────────────────────────────────────────
    rec         = db["recommendations"].find_one(sort=[("generated_at", -1)])
    rec_updated = (rec.get("generated_at", "")[:16].replace("T", " ")) if rec else "–"
    fixes       = []
    if rec:
        for f in rec.get("fixes", []):
            fixes.append({
                "rank":    f.get("rank", ""),
                "problem": f.get("problem", ""),
                "fix":     f.get("fix", ""),
                "where":   f.get("where", ""),
                "outcome": f.get("expected_outcome", ""),
            })

    # ── Chatbot QA with filters + pagination ──────────────────────────────
    cb_col  = prod["asbl_loft"]["conversations"]
    cb_sort_dir = 1 if cb_sort == "asc" else -1

    cb_query = {"status": {"$ne": "SKIPPED"}}
    if cb_status:
        cb_query["status"] = cb_status
    if cb_from or cb_to:
        cb_query["evaluated_at"] = {}
        if cb_from: cb_query["evaluated_at"]["$gte"] = cb_from
        if cb_to:   cb_query["evaluated_at"]["$lte"] = cb_to + "T23:59:59"

    cb_filtered = db["chatbot_qa"].count_documents(cb_query)
    cb_pages    = max(1, (cb_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
    cb_page     = min(cb_page, cb_pages)
    cb_offset   = (cb_page - 1) * PAGE_SIZE

    cb_docs = list(db["chatbot_qa"].find(
        cb_query,
        sort=[("evaluated_at", cb_sort_dir)],
        skip=cb_offset,
        limit=PAGE_SIZE
    ))

    conv_ids = [r.get("conversation_id") for r in cb_docs if r.get("conversation_id")]
    conv_map = {
        c["conversationId"]: c
        for c in cb_col.find({"conversationId": {"$in": conv_ids}})
        if c.get("conversationId")
    }

    chatbot_rows = []
    for r in cb_docs:
        cid  = r.get("conversation_id", "")
        conv = conv_map.get(cid, {})
        turns = []
        for t in conv.get("conversationDepth", []):
            u = (t.get("userText") or "").strip()
            b = strip_html(t.get("botText") or "").strip()
            if u or b:
                turns.append({"user": u[:300], "bot": b[:400]})
        chatbot_rows.append({
            "status":          r.get("status", "?"),
            "score":           r.get("score", "–"),
            "conversation_id": cid,
            "issues": [{"type": i.get("type","?"), "severity": i.get("severity","LOW"), "detail": i.get("detail","")}
                       for i in r.get("issues", [])],
            "summary":      (r.get("summary") or "")[:150],
            "evaluated_at": (r.get("evaluated_at") or "")[:16].replace("T", " "),
            "turns":        turns,
        })

    cb_total = db["chatbot_qa"].count_documents({"status": {"$ne": "SKIPPED"}})
    cb_fail  = db["chatbot_qa"].count_documents({"status": "FAIL"})
    cb_pass  = db["chatbot_qa"].count_documents({"status": "PASS"})

    # ── Voice QA with pagination ──────────────────────────────────────────
    vc_col      = prod["ASBLVoiceBot"]["call_transcripts"]
    vc_total    = db["voice_qa"].count_documents({"status": {"$ne": "SKIPPED"}})
    vc_fail     = db["voice_qa"].count_documents({"status": "FAIL"})
    vc_pass     = db["voice_qa"].count_documents({"status": "PASS"})
    vc_pages    = max(1, (vc_total + PAGE_SIZE - 1) // PAGE_SIZE)
    vc_page     = min(vc_page, vc_pages)
    vc_offset   = (vc_page - 1) * PAGE_SIZE

    vc_docs = list(db["voice_qa"].find(
        {"status": {"$ne": "SKIPPED"}},
        sort=[("evaluated_at", -1)],
        skip=vc_offset,
        limit=PAGE_SIZE
    ))

    call_sids = [r.get("call_sid") for r in vc_docs if r.get("call_sid")]
    call_map  = {
        c["call_sid"]: c
        for c in vc_col.find({"call_sid": {"$in": call_sids}})
        if c.get("call_sid")
    }

    voice_rows = []
    for r in vc_docs:
        sid  = r.get("call_sid", "")
        call = call_map.get(sid, {})
        turns = [
            {"speaker": t.get("speaker","?"), "text": (t.get("text") or "").strip()[:400],
             "is_bot": t.get("speaker") == "Anandita"}
            for t in call.get("transcript", []) if (t.get("text") or "").strip()
        ]
        voice_rows.append({
            "status":   r.get("status", "?"),
            "score":    r.get("score", "–"),
            "call_sid": sid,
            "language": r.get("language_used", "–"),
            "issues": [{"type": i.get("type","?"), "severity": i.get("severity","LOW"), "detail": i.get("detail","")}
                       for i in r.get("issues", [])],
            "summary":      (r.get("summary") or "")[:150],
            "evaluated_at": (r.get("evaluated_at") or "")[:16].replace("T", " "),
            "turns":        turns,
        })

    return render_template_string(
        TEMPLATE, style=STYLE, now=now,
        health=health, flags=flags,
        an_updated=an_updated,
        problems=problems, fb_updated=fb_updated,
        fixes=fixes, rec_updated=rec_updated,
        chatbot_rows=chatbot_rows,
        cb_total=cb_total, cb_fail=cb_fail, cb_pass=cb_pass,
        cb_latest_at=cb_updated,
        cb_filtered=cb_filtered, cb_page=cb_page, cb_pages=cb_pages,
        cb_page_range=page_range(cb_page, cb_pages),
        cb_offset=cb_offset,
        cb_from=cb_from, cb_to=cb_to, cb_sort=cb_sort, cb_status=cb_status,
        voice_rows=voice_rows,
        vc_total=vc_total, vc_fail=vc_fail, vc_pass=vc_pass,
        vc_latest_at=vc_updated,
        vc_page=vc_page, vc_pages=vc_pages,
        vc_page_range=page_range(vc_page, vc_pages),
        vc_offset=vc_offset,
    )


if __name__ == "__main__":
    print("\n[Dashboard] Starting on http://localhost:5050")
    print("[Dashboard] Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
