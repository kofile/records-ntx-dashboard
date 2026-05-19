#!/usr/bin/env python3
"""
update_snapshots.py — Daily refresh utility for the Records NTX dashboard.

Reads a Jira HTML export, appends today's snapshot to snapshots.json, and writes
the result. DevOps wires this into whatever upload mechanism fits Neumo's ops
(scheduled Function App, Power Automate flow, manual run, etc).

Usage:
    python update_snapshots.py <jira_export.html> <snapshots.json> [--today YYYY-MM-DD]

Behavior:
    - Today's snapshot becomes the new "current" (tickets[], today, exported_at)
    - Previous current is moved into history[]
    - Snapshots with the same captured date are de-duplicated (latest wins)
    - history[] is sorted oldest first
    - spreadsheet and divergence data are preserved from the previous file

Dependencies: standard library only. Tested on Python 3.9+.
"""
import sys
import re
import json
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser

NTX = ["Dallas", "Denton", "Johnson", "Collin", "Jefferson"]


class JiraTableParser(HTMLParser):
    """Header-aware parser. Maps cells to named fields by column header text."""

    def __init__(self):
        super().__init__()
        self.in_header_row = False
        self.in_th = False
        self.in_tbody = False
        self.in_row = False
        self.in_td = False
        self.current_th_attrs = {}
        self.current_th_text = []
        self.current_row = []
        self.current_cell = []
        self.depth = 0
        self.rows = []
        self.headers = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and "rowHeader" in a.get("class", ""):
            self.in_header_row = True
        elif self.in_header_row and tag == "th":
            self.in_th = True
            self.current_th_attrs = a
            self.current_th_text = []
        elif tag == "tbody":
            self.in_tbody = True
        elif self.in_tbody and tag == "tr" and "issuerow" in a.get("class", ""):
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag == "td":
            self.in_td = True
            self.depth = 1
            self.current_cell = []
        elif self.in_td:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == "tr" and self.in_header_row:
            self.in_header_row = False
        elif tag == "th" and self.in_th:
            self.in_th = False
            self.headers.append({
                "data_id": self.current_th_attrs.get("data-id", ""),
                "label": " ".join("".join(self.current_th_text).split()),
            })
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag == "td" and self.in_td:
            self.depth -= 1
            if self.depth == 0:
                self.in_td = False
                self.current_row.append(" ".join("".join(self.current_cell).split()))
        elif self.in_td:
            self.depth -= 1

    def handle_data(self, data):
        if self.in_th:
            self.current_th_text.append(data)
        elif self.in_td:
            self.current_cell.append(data)


def family(s):
    s = (s or "").lower()
    if s in ("closed", "done"):
        return "Done"
    if s in ("verified on uat", "deployed to uat", "ready for uat",
             "ready to merge to uat", "ready for production"):
        return "In testing"
    if s in ("in dev", "ready for dev"):
        return "In dev"
    if s in ("requirements clarification", "waiting for info"):
        return "In triage"
    if s in ("on hold", "vanguard code dependency"):
        return "Blocked"
    if s == "open":
        return "Open"
    return "Other"


def delivery_bucket(s):
    """delivered (in customer hands), pending (dev done, release pending), open (everything else)."""
    x = (s or "").lower()
    if x in ("closed", "done"):
        return "delivered"
    if x in ("ready for production", "verified on uat", "deployed to uat"):
        return "pending"
    return "open"


def tenants_for(raw):
    """Normalize tenant strings — accepts 'Jefferson', 'Jefferson TX', 'Jefferson County TX'."""
    parts = [x.strip() for x in (raw or "").split(",") if x.strip()]
    matched = []
    for p in parts:
        base = re.sub(r"\s+(County\s+)?(TX|Texas)\s*$", "", p, flags=re.IGNORECASE).strip()
        if base in NTX:
            matched.append(base)
    return matched if matched else (["(other)"] if parts else ["(untagged)"])


def parse_date(s):
    if not s or not s.strip():
        return None
    m = re.search(r"(\d{1,2})/([A-Za-z]{3})/(\d{2})", s)
    if not m:
        return None
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
              "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    try:
        return datetime(2000 + int(m.group(3)), months[m.group(2)], int(m.group(1)))
    except (ValueError, KeyError):
        return None


def extract_delivery_targets(labels_raw):
    """Parse month-year labels like 'May-2026'. Multiple labels = slip history."""
    if not labels_raw:
        return []
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    tokens = re.split(r"[,;\s]+", labels_raw.strip())
    out = []
    for t in tokens:
        m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(\d{4})$",
                     t, re.IGNORECASE)
        if m:
            mi = months[m.group(1)[:3].lower()]
            yr = int(m.group(2))
            out.append({
                "label": f"{month_names[mi]}-{yr}",
                "month_index": mi - 1, "year": yr,
                "sortable": yr * 12 + (mi - 1),
            })
    out.sort(key=lambda x: x["sortable"])
    return out


def parse_jira_html(jira_html, today_dt):
    """Returns (tickets[], displaying_meta)."""
    parser = JiraTableParser()
    parser.feed(jira_html)

    header_index = {}
    for i, h in enumerate(parser.headers):
        if h["label"]:
            header_index[h["label"].lower()] = i
        if h["data_id"]:
            header_index[h["data_id"].lower()] = i

    def get(row, name):
        i = header_index.get(name.lower(), -1)
        return row[i] if 0 <= i < len(row) else ""

    tickets = []
    for r in parser.rows:
        key = get(r, "Key") or get(r, "issuekey")
        if not key:
            continue
        status = get(r, "Status")
        created = get(r, "Created")
        updated = get(r, "Updated")
        end_date = get(r, "End Date")
        tenant_raw = get(r, "Tenant")
        labels_raw = get(r, "Labels")

        fam = family(status)
        bucket = delivery_bucket(status)
        cdt = parse_date(created)
        udt = parse_date(updated)
        edt = parse_date(end_date)
        dts = extract_delivery_targets(labels_raw)

        tickets.append({
            "key": key,
            "summary": get(r, "Summary"),
            "project": key.split("-")[0],
            "issue_type": get(r, "Issue Type") or get(r, "issuetype"),
            "status": status,
            "status_family": fam,
            "delivery_bucket": bucket,
            "is_open": bucket == "open",
            "team": get(r, "Team") or "",
            "tenant_raw": tenant_raw,
            "tenants": tenants_for(tenant_raw),
            "created": created,
            "created_iso": cdt.strftime("%Y-%m-%d") if cdt else None,
            "age_days": (today_dt - cdt).days if cdt else None,
            "updated": updated,
            "updated_iso": udt.strftime("%Y-%m-%d") if udt else None,
            "end_date": end_date,
            "end_date_iso": edt.strftime("%Y-%m-%d") if edt else None,
            "ships_month": edt.strftime("%b %Y") if edt else None,
            "sprint": get(r, "Sprint"),
            "comments_count": get(r, "Comments"),
            "labels_raw": labels_raw,
            "delivery_targets": dts,
            "current_delivery_target": dts[-1] if dts else None,
        })

    # Extract "Displaying X issues at Y" from the document — permissive of HTML tags
    m = re.search(r"Displaying\s+\d+\s+issues at\s+(?:<[^>]+>)?\s*([^<]+)", jira_html)
    label = m.group(1).strip() if m else today_dt.strftime("%d %b %Y")
    return tickets, label


def main():
    ap = argparse.ArgumentParser(description="Update snapshots.json with a Jira HTML export.")
    ap.add_argument("jira_html", help="Path to Jira HTML export")
    ap.add_argument("snapshots_json", help="Path to snapshots.json (will be updated in place)")
    ap.add_argument("--captured-date",
                    help="The date this snapshot represents (YYYY-MM-DD). "
                         "If omitted, parses from Jira HTML 'Displaying at...' line; "
                         "falls back to today's date.",
                    default=None)
    ap.add_argument("--today",
                    help="DEPRECATED alias for --captured-date.",
                    default=None)
    ap.add_argument("--history-limit", type=int, default=60,
                    help="Max history entries to retain. Default: 60.")
    args = ap.parse_args()

    # Parse the new Jira export
    with open(args.jira_html, encoding="utf-8") as f:
        jira_html = f.read()

    # Determine captured date for this snapshot:
    #   1. Explicit --captured-date flag (for true backfills)
    #   2. Parse from Jira HTML's "Displaying at <date>" line
    #   3. Fall back to today
    captured_iso = args.captured_date or args.today
    if not captured_iso:
        # Try to parse from Jira HTML — look for DD/Mon/YY anywhere within 200 chars
        # of "Displaying", to tolerate HTML tags like <strong> around the date.
        m = re.search(r"Displaying[\s\S]{0,200}?(\d{1,2})/([A-Za-z]{3})/(\d{2})", jira_html)
        if m:
            months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                      "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
            try:
                yr = 2000 + int(m.group(3))
                mi = months[m.group(2)]
                da = int(m.group(1))
                captured_iso = f"{yr:04d}-{mi:02d}-{da:02d}"
            except (ValueError, KeyError):
                captured_iso = None
    if not captured_iso:
        captured_iso = datetime.now().strftime("%Y-%m-%d")
        print(f"NOTE: couldn't parse export date; using today ({captured_iso})", file=sys.stderr)

    captured_dt = datetime.strptime(captured_iso, "%Y-%m-%d")
    tickets, label = parse_jira_html(jira_html, captured_dt)
    if not tickets:
        print(f"ERROR: No tickets parsed from {args.jira_html}", file=sys.stderr)
        sys.exit(1)

    # Load existing snapshots.json
    with open(args.snapshots_json) as f:
        snaps = json.load(f)

    # Build full list: existing current + existing history + new snapshot
    # Then sort by date, latest becomes new current, everything else is history.
    all_snaps = list(snaps.get("history", []))
    existing_current = snaps.get("today")
    if existing_current:
        all_snaps.append({
            "captured": existing_current,
            "label": snaps.get("exported_at", existing_current),
            "tickets": snaps.get("tickets", []),
        })

    # New snapshot
    new_snap = {
        "captured": captured_iso,
        "label": label,
        "tickets": tickets,
    }
    all_snaps.append(new_snap)

    # Dedupe by captured date — new snapshot wins if same date
    by_date = {}
    for s in all_snaps:
        # If the date appears more than once, the new one (last in list) wins
        by_date[s["captured"]] = s
    sorted_snaps = sorted(by_date.values(), key=lambda s: s["captured"])

    # Latest by date is the new current
    new_current = sorted_snaps[-1]
    history = sorted_snaps[:-1]

    # Trim history
    if len(history) > args.history_limit:
        history = history[-args.history_limit:]

    # Update snapshots.json
    snaps["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snaps["today"] = new_current["captured"]
    snaps["exported_at"] = new_current["label"]
    snaps["tickets"] = new_current["tickets"]
    snaps["history"] = history

    # Write atomically
    tmp = args.snapshots_json + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snaps, f, indent=2)
    import os
    os.replace(tmp, args.snapshots_json)

    is_backfill = captured_iso != new_current["captured"]
    print(f"OK: updated {args.snapshots_json}")
    print(f"  uploaded: {captured_iso} ({len(tickets)} tickets, label='{label}')")
    print(f"  current snapshot: {new_current['captured']}{'  [BACKFILL — current unchanged]' if is_backfill else '  [new current]'}")
    print(f"  history: {len(history)} prior snapshot(s)")


if __name__ == "__main__":
    main()
