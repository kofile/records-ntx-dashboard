#!/usr/bin/env python3
"""
read_cluster_registry.py — Read the Confluence registry page and emit the cluster list.

The cluster registry lives in a Confluence page (titled "Records Dashboard —
Active Clusters" by default). This script fetches the page via Confluence's
REST API, parses the cluster table, and writes the cluster list to clusters.json.

The dashboard's scheduled-refresh workflow calls this on every run to refresh
the cluster registry before fetching per-cluster Jira data.

Usage:
    python3 read_cluster_registry.py \
        --host neumo.atlassian.net \
        --user mandy.miller@neumo.com \
        --token <api-token> \
        --page-id 1234567890 \
        --output clusters.json

If the Confluence read fails, the script EXITS WITH CODE 2 *without* writing
clusters.json. The workflow's downstream steps fall back to the existing
clusters.json (last known good list). This makes the dashboard resilient to
brief Confluence outages.

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
from datetime import datetime, timezone
from html.parser import HTMLParser


# ----------------------------------------------------------------------
# Confluence API call
# ----------------------------------------------------------------------

def fetch_page_html(host: str, user: str, token: str, page_id: str) -> str:
    """Fetch a Confluence page's body in storage format (HTML-ish XML)."""
    url = f"https://{host}/wiki/api/v2/pages/{page_id}?body-format=storage"
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR: Confluence API HTTP {e.code} — {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("  Most likely: JIRA_TOKEN expired or revoked. Generate a new one at", file=sys.stderr)
            print("  https://id.atlassian.com/manage-profile/security/api-tokens", file=sys.stderr)
        elif e.code == 404:
            print(f"  Page ID {page_id} not found. Verify the page exists and the", file=sys.stderr)
            print("  service account has read access.", file=sys.stderr)
        raise
    body = data.get("body", {}).get("storage", {}).get("value")
    if not body:
        raise ValueError("Confluence page body is empty or missing")
    return body


# ----------------------------------------------------------------------
# Storage-format HTML parser
# ----------------------------------------------------------------------
# Confluence storage format is XHTML with some custom tags. Tables look like
# normal <table><tr><th>...</th></tr><tr><td>...</td></tr></table>. We find
# the first table on the page that has a "Jira filter ID" column.

class ClusterTableParser(HTMLParser):
    """Find the cluster table and extract rows.

    Robust to:
      - Confluence wrapping cells in <p>, <strong>, etc.
      - Color macros, status lozenges, and other inline noise
      - Extra columns added to the right of the required ones
      - Whitespace inside cells

    Brittle to:
      - Header text being renamed (e.g., "Filter ID" instead of "Jira filter ID")
      - The "Jira filter ID" column being deleted entirely
    """

    REQUIRED_COLUMNS = ["cluster name", "jira filter id"]

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.cell_buffer = []
        self.current_row = []
        self.tables = []         # list of {headers, rows}
        self.current_table = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = {"headers": None, "rows": []}
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell_buffer = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            text = " ".join("".join(self.cell_buffer).split()).strip()
            self.current_row.append(text)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                if self.current_table["headers"] is None:
                    self.current_table["headers"] = [c.lower() for c in self.current_row]
                else:
                    self.current_table["rows"].append(self.current_row)
            self.in_row = False
        elif tag == "table" and self.in_table:
            if self.current_table["headers"]:
                self.tables.append(self.current_table)
            self.current_table = None
            self.in_table = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buffer.append(data)

    def find_cluster_table(self):
        """Return the first parsed table whose headers include the required columns."""
        for table in self.tables:
            headers = table["headers"] or []
            if all(req in headers for req in self.REQUIRED_COLUMNS):
                return table
        return None


# ----------------------------------------------------------------------
# Cluster extraction
# ----------------------------------------------------------------------

def extract_clusters(page_html: str) -> list:
    """Parse the registry page and return a list of {id, title} clusters."""
    parser = ClusterTableParser()
    parser.feed(page_html)
    table = parser.find_cluster_table()
    if table is None:
        raise ValueError(
            "Could not find a cluster table on the registry page.\n"
            "Expected a table with columns including 'Cluster name' and 'Jira filter ID'.\n"
            f"Tables found: {len(parser.tables)}; their headers: "
            f"{[t['headers'] for t in parser.tables]}"
        )

    name_idx = table["headers"].index("cluster name")
    id_idx = table["headers"].index("jira filter id")

    clusters = []
    skipped = []
    for row in table["rows"]:
        if len(row) <= max(name_idx, id_idx):
            skipped.append({"row": row, "reason": "too few cells"})
            continue
        title = row[name_idx].strip()
        id_raw = row[id_idx].strip()
        # Tolerate "#29799" or "29799"
        id_raw = id_raw.lstrip("#").strip()
        if not title or not id_raw:
            skipped.append({"row": row, "reason": "empty title or id"})
            continue
        try:
            filter_id = int(id_raw)
        except ValueError:
            skipped.append({"row": row, "reason": f"non-integer id: {id_raw!r}"})
            continue
        clusters.append({"id": filter_id, "title": title})

    if skipped:
        print(f"WARNING: skipped {len(skipped)} row(s) while parsing:", file=sys.stderr)
        for s in skipped:
            print(f"  - {s['reason']}: {s['row']}", file=sys.stderr)

    if not clusters:
        raise ValueError(
            "Cluster table found but no valid rows extracted. Check that at "
            "least one row has a non-empty Cluster name and a numeric Jira filter ID."
        )

    return clusters


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", required=True, help="Confluence host, e.g. neumo.atlassian.net")
    ap.add_argument("--user", required=True, help="Atlassian user email")
    ap.add_argument("--token", required=True, help="Atlassian API token")
    ap.add_argument("--page-id", required=True, help="Confluence page ID of the registry page")
    ap.add_argument("--output", default="clusters.json", help="Path to write clusters.json")
    args = ap.parse_args()

    print(f"Fetching Confluence page {args.page_id} from {args.host}...", file=sys.stderr)
    try:
        page_html = fetch_page_html(args.host, args.user, args.token, args.page_id)
    except Exception as e:
        print(f"FATAL: could not fetch registry page: {e}", file=sys.stderr)
        print("Skipping clusters.json update. Workflow will use the previous list.", file=sys.stderr)
        sys.exit(2)

    print(f"Got page HTML: {len(page_html)} chars. Parsing cluster table...", file=sys.stderr)
    try:
        clusters = extract_clusters(page_html)
    except Exception as e:
        print(f"FATAL: could not parse cluster table: {e}", file=sys.stderr)
        print("Skipping clusters.json update. Workflow will use the previous list.", file=sys.stderr)
        sys.exit(2)

    print(f"Parsed {len(clusters)} cluster(s):", file=sys.stderr)
    for c in clusters:
        print(f"  - id={c['id']:<6} title={c['title']!r}", file=sys.stderr)

    output = {
        "_comment": (
            "Auto-generated from the Confluence registry page on every refresh. "
            "DO NOT EDIT THIS FILE BY HAND — your changes will be overwritten. "
            "Edit the Confluence page instead. The page ID is in the workflow file."
        ),
        "_source": {
            "type": "confluence_page",
            "host": args.host,
            "page_id": args.page_id,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "clusters": clusters,
    }

    tmp = args.output + ".tmp"
    with open(tmp, "w") as f:
        json.dump(output, f, indent=2)
    os.replace(tmp, args.output)
    print(f"OK: wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
