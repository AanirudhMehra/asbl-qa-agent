"""
ASBL QA — Google Sheets Reporter

Creates a new tab for every pipeline run.
Also maintains a running Index tab with one row per run.

Sheet ID: 1l-as7nNONYTZ2QUYmhiDdAiNLEGmVtdS-z_3qC8Ina4
"""

import os
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SHEET_ID    = "1l-as7nNONYTZ2QUYmhiDdAiNLEGmVtdS-z_3qC8Ina4"
KEY_FILE    = os.path.join(os.path.dirname(__file__), "google_service_account.json")
SCOPES      = ["https://www.googleapis.com/auth/spreadsheets",
               "https://www.googleapis.com/auth/drive"]

# ── Colours (RGB as hex strings for gspread) ─────────────────────────────────
COL_DARK_BLUE  = {"red": 0.10, "green": 0.22, "blue": 0.42}
COL_ORANGE     = {"red": 0.91, "green": 0.42, "blue": 0.12}
COL_GREEN_BG   = {"red": 0.83, "green": 0.95, "blue": 0.85}
COL_RED_BG     = {"red": 0.98, "green": 0.84, "blue": 0.84}
COL_YELLOW_BG  = {"red": 1.00, "green": 0.95, "blue": 0.80}
COL_GREY_BG    = {"red": 0.95, "green": 0.95, "blue": 0.95}
COL_WHITE      = {"red": 1.00, "green": 1.00, "blue": 1.00}
COL_HEADER_TXT = {"red": 1.00, "green": 1.00, "blue": 1.00}


def _client():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _cell_format(bg=None, bold=False, font_size=10, txt_color=None, halign=None):
    fmt = {
        "textFormat": {
            "bold": bold,
            "fontSize": font_size,
        }
    }
    if bg:
        fmt["backgroundColor"] = bg
    if txt_color:
        fmt["textFormat"]["foregroundColor"] = txt_color
    if halign:
        fmt["horizontalAlignment"] = halign
    return fmt


def _status_bg(status):
    s = (status or "").upper()
    if s == "PASS":    return COL_GREEN_BG
    if s == "FAIL":    return COL_RED_BG
    if s == "SKIPPED": return COL_GREY_BG
    return COL_WHITE


def _severity_bg(severity):
    s = (severity or "").upper()
    if s == "HIGH":   return COL_RED_BG
    if s == "MEDIUM": return COL_YELLOW_BG
    if s == "LOW":    return COL_GREEN_BG
    return COL_WHITE


# ════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def write_run_to_sheet(run_data: dict):
    """
    run_data keys:
      run_time      str  "2026-05-22 14:00"
      window        str  "11:00 → 14:00"
      cb_results    list of chatbot_qa docs
      vc_results    list of voice_qa docs
      an_flags      list of analytics flag dicts
      problems      list of feedback problem dicts
      fixes         list of recommendation fix dicts
    """
    gc       = _client()
    sheet    = gc.open_by_key(SHEET_ID)
    run_time = run_data.get("run_time", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # ── Create new tab ────────────────────────────────────────────────────
    tab_title = run_time
    try:
        ws = sheet.add_worksheet(title=tab_title, rows=600, cols=15)
    except Exception:
        ws = sheet.worksheet(tab_title)
        ws.clear()

    # ── Build ALL data in memory first, then write in ONE call ────────────
    all_rows   = []   # list of lists — full sheet content
    fmt_reqs   = []   # formatting requests keyed to row indices

    cb_results = run_data.get("cb_results", [])
    cb_flagged = run_data.get("cb_flagged", [])
    vc_results = run_data.get("vc_results", [])
    an_flags   = run_data.get("an_flags", [])
    problems   = run_data.get("problems", [])
    fixes      = run_data.get("fixes", [])

    cb_pass    = sum(1 for r in cb_results if r.get("status") == "PASS")
    cb_fail    = sum(1 for r in cb_results if r.get("status") == "FAIL")
    cb_tot     = cb_pass + cb_fail
    cb_spam    = len(cb_flagged)
    cb_spam_pct = round(cb_spam / (cb_tot + cb_spam) * 100, 1) if (cb_tot + cb_spam) > 0 else 0
    vc_pass    = sum(1 for r in vc_results if r.get("status") == "PASS")
    vc_fail    = sum(1 for r in vc_results if r.get("status") == "FAIL")
    vc_tot     = vc_pass + vc_fail
    cb_health  = round((1 - cb_fail / cb_tot) * 10, 1) if cb_tot else "–"
    vc_health  = round((1 - vc_fail / vc_tot) * 10, 1) if vc_tot else "–"
    high_flags = sum(1 for f in an_flags if f.get("severity") == "HIGH")
    an_health  = max(0.0, round(10 - high_flags * 1.5, 1)) if an_flags else "–"

    def add_section(title, col_count=8):
        r = len(all_rows)
        all_rows.append([title] + [""] * (col_count - 1))
        fmt_reqs.append({"repeatCell": {"range": {"sheetId": ws.id,
            "startRowIndex": r, "endRowIndex": r+1,
            "startColumnIndex": 0, "endColumnIndex": col_count},
            "cell": {"userEnteredFormat": _cell_format(bg=COL_DARK_BLUE, bold=True,
                font_size=11, txt_color=COL_HEADER_TXT)},
            "fields": "userEnteredFormat"}})
        fmt_reqs.append({"mergeCells": {"range": {"sheetId": ws.id,
            "startRowIndex": r, "endRowIndex": r+1,
            "startColumnIndex": 0, "endColumnIndex": col_count},
            "mergeType": "MERGE_ALL"}})

    def add_col_header(headers):
        r = len(all_rows)
        all_rows.append(headers)
        fmt_reqs.append({"repeatCell": {"range": {"sheetId": ws.id,
            "startRowIndex": r, "endRowIndex": r+1,
            "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "cell": {"userEnteredFormat": _cell_format(bg=COL_ORANGE, bold=True,
                font_size=9, txt_color=COL_HEADER_TXT)},
            "fields": "userEnteredFormat"}})

    def add_data_row(data, bg=None, col_count=8):
        r = len(all_rows)
        all_rows.append(data)
        if bg:
            fmt_reqs.append({"repeatCell": {"range": {"sheetId": ws.id,
                "startRowIndex": r, "endRowIndex": r+1,
                "startColumnIndex": 0, "endColumnIndex": col_count},
                "cell": {"userEnteredFormat": _cell_format(bg=bg)},
                "fields": "userEnteredFormat.backgroundColor"}})

    # SECTION 1 — SUMMARY
    add_section("RUN SUMMARY", col_count=4)
    for row_data in [
        ["Run Time",              run_time],
        ["Window",                run_data.get("window", "–")],
        ["Chatbot Evaluated",     cb_tot],
        ["Chatbot Pass",          cb_pass],
        ["Chatbot Fail",          cb_fail],
        ["Chatbot Health",        f"{cb_health}/10"],
        ["CB Flagged (Spam)",     cb_spam],
        ["CB Spam %",             f"{cb_spam_pct}%"],
        ["LLM Calls Saved",       cb_spam],
        ["Voice Evaluated",       vc_tot],
        ["Voice Pass",            vc_pass],
        ["Voice Fail",            vc_fail],
        ["Voice Health",          f"{vc_health}/10"],
        ["Analytics Flags",       len(an_flags)],
        ["HIGH Flags",            high_flags],
        ["Analytics Health",      f"{an_health}/10"],
        ["Problems Found",        len(problems)],
        ["Fixes Generated",       len(fixes)],
    ]:
        all_rows.append(row_data)
    all_rows.append([])  # blank row

    # SECTION 2 — CHATBOT QA
    add_section("CHATBOT QA RESULTS", col_count=8)
    add_col_header(["#", "Status", "Score", "Conversation ID", "Issue Types", "Severity", "Detail", "Evaluated At"])
    if cb_results:
        for i, r in enumerate(cb_results, 1):
            issues = r.get("issues", [])
            add_data_row([
                i,
                r.get("status", "–"),
                r.get("score", "–"),
                r.get("conversation_id", "–"),
                ", ".join(x.get("type", "") for x in issues) or "–",
                ", ".join(x.get("severity", "") for x in issues) or "–",
                " | ".join(x.get("detail", "")[:80] for x in issues) or "–",
                (r.get("evaluated_at") or "")[:16].replace("T", " "),
            ], bg=_status_bg(r.get("status")), col_count=8)
    else:
        all_rows.append(["No chatbot conversations evaluated in this window."])
    all_rows.append([])

    # SECTION 3 — FLAGGED MESSAGES
    add_section("FLAGGED USER MESSAGES (Spam Filter)", col_count=5)
    add_col_header(["#", "Conversation ID", "Turn", "Flag Type", "User Message"])
    if cb_flagged:
        COL_AMBER = {"red": 1.00, "green": 0.80, "blue": 0.40}
        for i, r in enumerate(cb_flagged, 1):
            flags = r.get("user_flags", [])
            if flags:
                for fl in flags:
                    add_data_row([
                        i,
                        r.get("conversation_id", "–"),
                        fl.get("turn", "–"),
                        fl.get("type", "–"),
                        fl.get("text", "–")[:150],
                    ], bg=COL_AMBER, col_count=5)
            else:
                add_data_row([
                    i,
                    r.get("conversation_id", "–"),
                    "–", "SPAM_FILTERED", "–",
                ], bg=COL_AMBER, col_count=5)
    else:
        all_rows.append(["No spam-filtered conversations in this window."])
    all_rows.append([])

    # SECTION 4 — VOICE QA RESULTS
    add_section("VOICE QA RESULTS", col_count=9)
    add_col_header(["#", "Status", "Score", "Call SID", "Language", "Lang Compliance", "Issue Types", "Detail", "Evaluated At"])
    if vc_results:
        for i, r in enumerate(vc_results, 1):
            issues = r.get("issues", [])
            add_data_row([
                i,
                r.get("status", "–"),
                r.get("score", "–"),
                r.get("call_sid", "–"),
                r.get("language_used", "–"),
                r.get("language_compliance", "–"),
                ", ".join(x.get("type", "") for x in issues) or "–",
                " | ".join(x.get("detail", "")[:80] for x in issues) or "–",
                (r.get("evaluated_at") or "")[:16].replace("T", " "),
            ], bg=_status_bg(r.get("status")), col_count=9)
    else:
        all_rows.append(["No voice calls evaluated in this window."])
    all_rows.append([])

    # SECTION 4 — ANALYTICS FLAGS
    add_section("ANALYTICS FLAGS", col_count=4)
    add_col_header(["Severity", "Source", "Type", "Detail"])
    if an_flags:
        for f in an_flags:
            add_data_row([
                f.get("severity", "–"),
                f.get("source", "–"),
                f.get("type", "–"),
                f.get("detail", "–")[:200],
            ], bg=_severity_bg(f.get("severity")), col_count=4)
    else:
        all_rows.append(["No analytics flags in this run."])
    all_rows.append([])

    # SECTION 5 — PROBLEMS
    add_section("PROBLEMS FOUND", col_count=5)
    add_col_header(["Urgency", "Title", "What's Wrong", "What's NOT Wrong", "Evidence"])
    if problems:
        for p in problems:
            add_data_row([
                p.get("urgency", "–"),
                p.get("title", "–"),
                p.get("what_is_wrong", "–")[:200],
                p.get("what_is_not_wrong", "–")[:200],
                " | ".join(p.get("evidence", [])[:3])[:200],
            ], bg=_severity_bg(p.get("urgency")), col_count=5)
    else:
        all_rows.append(["No problems identified in this run."])
    all_rows.append([])

    # SECTION 6 — FIXES
    add_section("RECOMMENDED FIXES", col_count=6)
    add_col_header(["Rank", "Problem", "Fix", "Where", "Change Type", "Expected Outcome"])
    if fixes:
        for f in fixes:
            add_data_row([
                f.get("rank", "–"),
                f.get("problem", f.get("problem_title", "–"))[:100],
                f.get("fix", "–")[:200],
                f.get("where", "–")[:100],
                f.get("change_type", "–"),
                f.get("expected_outcome", f.get("outcome", "–"))[:200],
            ], col_count=6)
    else:
        all_rows.append(["No fixes generated in this run."])

    # ── ONE write call for all data ───────────────────────────────────────
    ws.update("A1", all_rows, value_input_option="RAW")
    time.sleep(2)  # brief pause before formatting to avoid quota

    # ── ONE batch call for all formatting ─────────────────────────────────
    if fmt_reqs:
        sheet.batch_update({"requests": fmt_reqs})
        time.sleep(2)

    # ── Column widths ─────────────────────────────────────────────────────
    sheet.batch_update({"requests": [
        {
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 40},
                "fields": "pixelSize"
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 80},
                "fields": "pixelSize"
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 3, "endIndex": 4},
                "properties": {"pixelSize": 220},
                "fields": "pixelSize"
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 6, "endIndex": 7},
                "properties": {"pixelSize": 300},
                "fields": "pixelSize"
            }
        },
    ]})

    print(f"[Sheets] Tab '{tab_title}' written — {len(all_rows)} rows")

    # ── Update Index tab ──────────────────────────────────────────────────
    _update_index(sheet, run_time, run_data.get("window", "–"),
                  cb_tot, cb_pass, cb_fail, cb_health, cb_spam,
                  vc_tot, vc_pass, vc_fail, vc_health,
                  len(an_flags), high_flags, an_health,
                  len(problems), len(fixes), tab_title)


def _update_index(sheet, run_time, window,
                  cb_tot, cb_pass, cb_fail, cb_health, cb_spam,
                  vc_tot, vc_pass, vc_fail, vc_health,
                  total_flags, high_flags, an_health,
                  n_problems, n_fixes, tab_title):

    HEADERS = [
        "Run Time", "Window",
        "CB Evaluated", "CB Pass", "CB Fail", "CB Health", "CB Flagged",
        "VC Evaluated", "VC Pass", "VC Fail", "VC Health",
        "Total Flags", "HIGH Flags", "Analytics Health",
        "Problems", "Fixes", "Tab"
    ]

    try:
        idx = sheet.worksheet("Index")
    except gspread.exceptions.WorksheetNotFound:
        idx = sheet.add_worksheet(title="Index", rows=200, cols=len(HEADERS))
        idx.update("A1", [HEADERS], value_input_option="RAW")
        # Format header row
        sheet.batch_update({"requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": idx.id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 0, "endColumnIndex": len(HEADERS),
                },
                "cell": {"userEnteredFormat": _cell_format(
                    bg=COL_DARK_BLUE, bold=True,
                    txt_color=COL_HEADER_TXT
                )},
                "fields": "userEnteredFormat"
            }
        }]})

    new_row = [
        run_time, window,
        cb_tot, cb_pass, cb_fail, f"{cb_health}/10", cb_spam,
        vc_tot, vc_pass, vc_fail, f"{vc_health}/10",
        total_flags, high_flags, f"{an_health}/10",
        n_problems, n_fixes, tab_title
    ]
    idx.append_row(new_row, value_input_option="RAW")
    print(f"[Sheets] Index updated — {run_time}")


# ════════════════════════════════════════════════════════════════════════════
# QUICK TEST
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("[Sheets] Running connection test...")
    gc    = _client()
    sheet = gc.open_by_key(SHEET_ID)
    print(f"[Sheets] Connected — '{sheet.title}'")
    print("[Sheets] Test passed.")
