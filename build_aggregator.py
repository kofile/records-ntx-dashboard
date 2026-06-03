#!/usr/bin/env python3
"""
build_aggregator.py — Rebuild the dashboard's entry-point snapshots.json.

Reads clusters.json to see which clusters are registered, then reads each
snapshots-<id>.json file and assembles the aggregator.

The aggregator file (snapshots.json) is what the dashboard loads on page open.
It contains:
  - A list of clusters with their per-cluster snapshot URLs
  - A backward-compatible mirror of the default cluster's data (so a viewer
    with a stale cache or an older index.html still sees the N TX dashboard)

Usage:
    python3 build_aggregator.py
    python3 build_aggregator.py --clusters clusters.json --output snapshots.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clusters", default="clusters.json", help="Path to clusters.json")
    ap.add_argument("--output", default="snapshots.json", help="Path to write aggregator")
    args = ap.parse_args()

    if not os.path.exists(args.clusters):
        print(f"ERROR: {args.clusters} not found", file=sys.stderr)
        sys.exit(1)

    with open(args.clusters) as f:
        registry = json.load(f)

    clusters = registry.get("clusters", [])
    if not clusters:
        print("ERROR: clusters.json has no clusters registered", file=sys.stderr)
        sys.exit(1)

    # The first cluster in the registry is the default — the one whose data
    # mirrors into the aggregator's top-level fields for backward compatibility.
    default = clusters[0]
    default_id = default["id"]
    default_snap_path = f"snapshots-{default_id}.json"

    if not os.path.exists(default_snap_path):
        print(f"WARNING: {default_snap_path} not found — default cluster has no data yet",
              file=sys.stderr)
        default_data = {
            "today": None,
            "exported_at": None,
            "tickets": [],
            "history": [],
            "spreadsheet": {},
            "divergence": {},
        }
    else:
        with open(default_snap_path) as f:
            default_data = json.load(f)

    # Build the cluster manifest — only include clusters whose data file exists
    cluster_manifest = []
    for c in clusters:
        snap_path = f"snapshots-{c['id']}.json"
        entry = {
            "id": c["id"],
            "title": c["title"],
            "snapshot_url": f"./{snap_path}",
        }
        if os.path.exists(snap_path):
            with open(snap_path) as f:
                cdata = json.load(f)
            entry["today"] = cdata.get("today")
            entry["ticket_count"] = len(cdata.get("tickets", []))
            entry["updated_at"] = cdata.get("updated_at")
        else:
            # Cluster registered but no data yet (next scheduled run will populate)
            entry["today"] = None
            entry["ticket_count"] = 0
            entry["updated_at"] = None
        cluster_manifest.append(entry)

    out = {
        "_schema": "v2-multi-cluster",
        "_comment": (
            "Aggregator file. The dashboard loads this first. The 'clusters' "
            "array tells the dashboard which per-cluster snapshot files to fetch. "
            "The legacy single-cluster fields (today/tickets/history) mirror the "
            "default cluster's data for backward compatibility."
        ),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "default_cluster_id": default_id,
        "clusters": cluster_manifest,
        # Legacy mirror — backward compatibility
        "today": default_data.get("today"),
        "exported_at": default_data.get("exported_at"),
        "tickets": default_data.get("tickets", []),
        "history": default_data.get("history", []),
        "spreadsheet": default_data.get("spreadsheet", {}),
        "divergence": default_data.get("divergence", {}),
    }

    tmp = args.output + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, args.output)

    print(f"OK: wrote {args.output}", file=sys.stderr)
    print(f"  Default cluster: id={default_id}, title='{default['title']}'", file=sys.stderr)
    print(f"  Clusters in manifest: {len(cluster_manifest)}", file=sys.stderr)
    for c in cluster_manifest:
        status = f"{c['ticket_count']} tickets" if c['today'] else "(no data yet)"
        print(f"    [{c['id']}] {c['title']}: {status}", file=sys.stderr)


if __name__ == "__main__":
    main()
