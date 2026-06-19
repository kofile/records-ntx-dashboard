#!/usr/bin/env python3
"""
fetch_jira_filter.py — Pull a Jira filter via REST API and write snapshots.json.

Used by the scheduled refresh workflow. Replaces the daily manual HTML export.

Usage:
    python3 fetch_jira_filter.py \
        --host neumo.atlassian.net \
        --user mandy.miller@neumo.com \
        --token <api-token> \
        --filter-id 29799 \
        --output snapshots.json

Behavior:
    - Uses JQL `filter = <ID>` to fetch all matching issues
    - Paginates if more than 100 results
    - Maps Jira fields to the dashboard's ticket structure
    - Loads existing snapshots.json; moves current to history; sets new current
    - Atomic write

Dependencies: standard library only (Python 3.9+).
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Custom field IDs (from Mandy's Jira tenant)
CF_END_DATE = "customfield_11476"
CF_TENANT = "customfield_11465"


# --------------------------------------------------------------------------
# Bucket / family logic — MUST match index.html's JS exactly
# --------------------------------------------------------------------------

def family(s):
    s = (s or "").lower()
    if s in ("closed", "done"):
        return "Done"
    if s in ("verified on uat", "deployed to uat", "ready for uat",
             "ready to merge to uat", "ready to test on uat", "testing on uat",
             "ready to test", "ready for production", "verify production"):
        return "In testing"
    if s in ("in dev", "ready for dev", "ready for development"):
        return "In dev"
    if s in ("requirements clarification", "waiting for info", "discovery & design"):
        return "In triage"
    if s in ("on hold", "vanguard code dependency", "parking lot"):
        return "Blocked"
    if s == "open":
        return "Open"
    return "Other"


def delivery_bucket(s):
    """4-stage bucket — mirrors JS deliveryBucket() in index.html."""
    x = (s or "").lower().strip()
    if x in ("closed", "done"):
        return "delivered"
    if x in ("ready for production", "verified on uat", "deployed to uat", "verify production"):
        return "pending_release"
    if x in ("in dev", "ready for uat", "ready to merge to uat",
             "ready to test on uat", "testing on uat", "ready to test"):
        return "in_progress"
    return "open"


def tenants_for(raw):
    """Parse comma-separated tenant strings; strip common suffixes (TX, Texas, County).

    Mirrors the JS tenantsFor() in index.html. No longer gated by an NTX-5
    allowlist — any non-empty tenant flows through. This lets Customer Prep
    surface new tenants dynamically as they appear in the data.

    Examples:
      "Collin"             -> ["Collin"]
      "Jefferson TX"       -> ["Jefferson"]
      "Anderson, Collin"   -> ["Anderson", "Collin"]
      "Lake County IL"     -> ["Lake County IL"]  (only TX/Texas suffixes stripped)
      "All"                -> ["All"]
      ""                   -> ["(untagged)"]
    """
    parts = [x.strip() for x in (raw or "").split(",") if x.strip()]
    cleaned = []
    for p in parts:
        base = re.sub(r"\s+(County\s+)?(TX|Texas)\s*$", "", p, flags=re.IGNORECASE).strip()
        if base:
            cleaned.append(base)
    return cleaned if cleaned else (["(other)"] if parts else ["(untagged)"])


def parse_iso_to_date(iso):
    """Parse a Jira ISO timestamp to a YYYY-MM-DD string. Returns None on failure."""
    if not iso:
        return None
    try:
        # Jira gives "2026-05-14T15:37:00.000-0400"
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00").rstrip())
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        # Older format: try cutting at T
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", iso)
        return m.group(1) if m else None


def days_between(iso_a, today_dt):
    """Days between an ISO timestamp and today_dt."""
    if not iso_a:
        return None
    try:
        dt_a = datetime.fromisoformat(iso_a.replace("Z", "+00:00").rstrip())
        dt_a = dt_a.replace(tzinfo=None)
        return (today_dt - dt_a).days
    except (ValueError, TypeError):
        return None


def extract_delivery_targets(labels):
    """Parse month-year labels like 'May-2026'. Multiple labels = slip history."""
    if not labels:
        return []
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    out = []
    for label in labels:
        m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(\d{4})$",
                     label, re.IGNORECASE)
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


# --------------------------------------------------------------------------
# Jira API client (stdlib only)
# --------------------------------------------------------------------------

def jira_request(host, user, token, path, method="GET", params=None, body=None):
    """Request against Jira REST API. Returns parsed JSON. Raises on non-2xx."""
    url = f"https://{host}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    }
    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Jira API error {e.code} at {path}: {body_text}") from e


def fetch_filter_issues(host, user, token, filter_id):
    """Fetch all issues matching a saved filter via /rest/api/3/search/jql.

    Uses the new endpoint (POST + cursor pagination via nextPageToken).
    The old /rest/api/3/search endpoint was removed by Atlassian in 2025.
    """
    jql = f"filter = {filter_id}"
    fields = [
        "issuetype", "summary", "status", "created", "updated",
        "labels", "customfield_10019",  # Sprint
        CF_END_DATE, CF_TENANT,
        "comment", "reporter",
    ]
    all_issues = []
    next_token = None
    page_size = 100
    while True:
        body = {
            "jql": jql,
            "fields": fields,
            "maxResults": page_size,
        }
        if next_token:
            body["nextPageToken"] = next_token
        page = jira_request(host, user, token, "/rest/api/3/search/jql",
                           method="POST", body=body)
        issues = page.get("issues", [])
        all_issues.extend(issues)
        next_token = page.get("nextPageToken")
        is_last = page.get("isLast", True)
        if is_last or not next_token or not issues:
            break
    return all_issues


# --------------------------------------------------------------------------
# Transformation: Jira issue → dashboard ticket
# --------------------------------------------------------------------------

def transform_issue(issue, today_dt):
    fields = issue.get("fields", {})
    key = issue.get("key", "")
    status = (fields.get("status") or {}).get("name", "") or ""
    summary = fields.get("summary", "") or ""
    issue_type = (fields.get("issuetype") or {}).get("name", "") or ""

    # Tenant (multiselect custom field — may be list or single)
    tenant_field = fields.get(CF_TENANT)
    if isinstance(tenant_field, list):
        tenant_raw = ", ".join(v.get("value", "") if isinstance(v, dict) else str(v)
                              for v in tenant_field)
    elif isinstance(tenant_field, dict):
        tenant_raw = tenant_field.get("value", "") or ""
    else:
        tenant_raw = str(tenant_field or "")

    # Labels
    labels = fields.get("labels", []) or []
    labels_raw = ", ".join(labels)

    # End Date
    end_date_iso = fields.get(CF_END_DATE)  # date format YYYY-MM-DD
    end_date_str = end_date_iso or ""

    created = fields.get("created", "") or ""
    updated = fields.get("updated", "") or ""
    created_iso = parse_iso_to_date(created)
    updated_iso = parse_iso_to_date(updated)
    end_date_clean = parse_iso_to_date(end_date_iso) if end_date_iso else None

    age_days = days_between(created, today_dt)

    fam = family(status)
    bucket = delivery_bucket(status)
    dts = extract_delivery_targets(labels)

    # Reporter
    reporter_field = fields.get("reporter") or {}
    reporter = reporter_field.get("displayName", "") or ""

    # Sprint
    sprint_raw = fields.get("customfield_10019") or []
    sprint = ""
    if isinstance(sprint_raw, list) and sprint_raw:
        first = sprint_raw[0]
        if isinstance(first, dict):
            sprint = first.get("name", "")
        else:
            # Older format: "com.atlassian.greenhopper.service.sprint.Sprint@...[name=Sprint 12,...]"
            m = re.search(r"name=([^,]+)", str(first))
            sprint = m.group(1) if m else ""

    # Comments count
    comment_block = fields.get("comment") or {}
    comments_count = comment_block.get("total", 0) if isinstance(comment_block, dict) else 0

    # Ships-month for Tile 2
    ships_month = None
    if end_date_clean:
        try:
            dt = datetime.strptime(end_date_clean, "%Y-%m-%d")
            ships_month = dt.strftime("%b %Y")
        except ValueError:
            pass

    return {
        "key": key,
        "summary": summary,
        "project": key.split("-")[0] if "-" in key else "",
        "issue_type": issue_type,
        "status": status,
        "status_family": fam,
        "delivery_bucket": bucket,
        "is_open": bucket == "open",
        "reporter": reporter,
        "tenant_raw": tenant_raw,
        "tenants": tenants_for(tenant_raw),
        "created": created,
        "created_iso": created_iso,
        "age_days": age_days,
        "updated": updated,
        "updated_iso": updated_iso,
        "end_date": end_date_str,
        "end_date_iso": end_date_clean,
        "ships_month": ships_month,
        "sprint": sprint,
        "comments_count": str(comments_count) if comments_count else "",
        "labels_raw": labels_raw,
        "delivery_targets": dts,
        "current_delivery_target": dts[-1] if dts else None,
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Fetch a Jira filter via REST API and write snapshots.json.")
    ap.add_argument("--host", required=True, help="Jira host, e.g. neumo.atlassian.net")
    ap.add_argument("--user", required=True, help="Jira user email")
    ap.add_argument("--token", required=True, help="Jira API token")
    ap.add_argument("--filter-id", required=True, help="Saved filter ID")
    ap.add_argument("--output", default="snapshots.json", help="Path to snapshots.json")
    args = ap.parse_args()

    print(f"Fetching filter {args.filter_id} from {args.host}...", file=sys.stderr)
    issues = fetch_filter_issues(args.host, args.user, args.token, args.filter_id)
    print(f"Got {len(issues)} issues", file=sys.stderr)
    if not issues:
        print("ERROR: filter returned zero issues. Aborting.", file=sys.stderr)
        sys.exit(1)

    today_dt = datetime.now()
    today_iso = today_dt.strftime("%Y-%m-%d")
    tickets = [transform_issue(i, today_dt) for i in issues]

    # Build label from today
    label = today_dt.strftime("%d %b %Y") + " (auto)"

    # Load existing snapshots.json if present, preserve spreadsheet+divergence
    if os.path.exists(args.output):
        with open(args.output) as f:
            existing = json.load(f)
    else:
        existing = {"history": [], "spreadsheet": {}, "divergence": {}}

    # Build full set: existing current + existing history + new snapshot
    all_snaps = list(existing.get("history", []))
    if existing.get("today"):
        all_snaps.append({
            "captured": existing["today"],
            "label": existing.get("exported_at", existing["today"]),
            "tickets": existing.get("tickets", []),
        })

    new_snap = {
        "captured": today_iso,
        "label": label,
        "tickets": tickets,
    }
    all_snaps.append(new_snap)

    # Dedupe by captured date — most recent wins (i.e., today replaces today)
    by_date = {}
    for s in all_snaps:
        by_date[s["captured"]] = s
    sorted_snaps = sorted(by_date.values(), key=lambda s: s["captured"])

    new_current = sorted_snaps[-1]
    history = sorted_snaps[:-1]

    # Trim history to last 60 entries
    if len(history) > 60:
        history = history[-60:]

    output = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "today": new_current["captured"],
        "exported_at": new_current["label"],
        "tickets": new_current["tickets"],
        "history": history,
        "spreadsheet": existing.get("spreadsheet", {}),
        "divergence": existing.get("divergence", {}),
    }

    tmp = args.output + ".tmp"
    with open(tmp, "w") as f:
        json.dump(output, f, indent=2)
    os.replace(tmp, args.output)

    print(f"OK: wrote {args.output}", file=sys.stderr)
    print(f"  current: {new_current['captured']} ({len(new_current['tickets'])} tickets)", file=sys.stderr)
    print(f"  history: {len(history)} prior snapshots", file=sys.stderr)


if __name__ == "__main__":
    main()
