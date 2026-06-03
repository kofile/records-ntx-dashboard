# Records — Escalation & Delivery Dashboard

A live dashboard tracking escalation and delivery for one or more Records Suite
clusters. Originally built for the North Texas support spike (May 2026);
generalized to host any escalation cluster.

**Live URL:** `https://<your-username>.github.io/records-ntx-spike/`
*(replace with your actual GitHub Pages URL once deployed)*

## What it shows (per active cluster)

Four tiles, each answering one question:

1. **Are we winning?** — Delivery rate, three-way split (delivered / pending / open), cumulative trend chart.
2. **What's committed and shipping** — Delivery target labels + production End Dates.
3. **Where's the bottleneck?** — Open tickets by stage, with aging.
4. **Customer pain** — Open count per tenant.

Plus a Customer Prep view for per-tenant client-safe summaries.

## Clusters

The dashboard supports multiple clusters. Each cluster is a Jira filter ID +
a display title. Switch between clusters using the pills above the toolbar.

**To add a new cluster:**
1. Click **"+ New cluster"** in the dashboard.
2. Enter a title and the Jira filter ID.
3. The dashboard creates a *local* cluster (visible only in your browser).
4. To make it visible to everyone, paste the shown JSON snippet into
   [`clusters.json`](./clusters.json) and commit it.
5. The next scheduled refresh (8am or 4pm ET) populates the cluster's data.

**To remove a cluster:** delete its entry from `clusters.json` and commit.
The cluster pill disappears for everyone on the next page load. The
per-cluster snapshot file (`snapshots-<id>.json`) becomes an orphan — safe to
leave alone, or delete manually.

## How the data flows

```
clusters.json (registry)
        │
        ▼
GitHub Actions (2× business day: 8am, 4pm ET)
        │  fetch_jira_filter.py per cluster
        ▼
snapshots-<filter_id>.json (one per cluster)
        │
        ▼
build_aggregator.py
        │
        ▼
snapshots.json (aggregator — what the dashboard reads first)
        │
        ▼
index.html (dashboard renders)
```

`snapshots.json` is the entry point — it lists the active clusters and
mirrors the default cluster's data for backward compatibility. Each cluster's
full data lives in its own `snapshots-<filter_id>.json` file.

## Refresh schedule

Auto-refresh runs **twice per business day** via GitHub Actions:
- **8:00 AM ET** (12:00 UTC)
- **4:00 PM ET** (20:00 UTC)

Monday through Friday only.

The schedule is defined in [`.github/workflows/scheduled-refresh.yml`](./.github/workflows/scheduled-refresh.yml).
Cron times are in UTC.

If the auto-refresh fails (e.g., expired API token, a deleted filter), an
issue is automatically opened in this repo with a runbook for fixing it.

## Manual backup workflow

If the auto-refresh is broken, the manual workflow still works:

1. Export Jira filter as HTML from `https://neumo.atlassian.net/issues/?filter=<id>`
2. Drop the file into [`jira-exports/`](./jira-exports/) via the GitHub web UI
3. The `update-snapshot.yml` workflow processes it and updates the **default
   cluster only** (N TX)
4. For other clusters, run `update_snapshots.py` locally pointing at the
   appropriate `snapshots-<id>.json` and push the result

Note: the manual workflow currently writes to the legacy single-file format.
After Mandy's transition, this is one of the things to either retire or
update to support per-cluster files.

## Repository structure

```
records-ntx-spike/
├── index.html                          The dashboard (single-page web app)
├── clusters.json                       The cluster registry (source of truth)
├── snapshots.json                      Aggregator file (entry point)
├── snapshots-29799.json                N TX cluster data
├── snapshots-<other-id>.json           One per registered cluster
├── fetch_jira_filter.py                Pulls one filter's data from Jira API
├── build_aggregator.py                 Rebuilds snapshots.json from per-cluster files
├── update_snapshots.py                 Manual-export fallback (default cluster)
├── jira-exports/                       Manual HTML exports (backup workflow)
├── .github/workflows/
│   ├── scheduled-refresh.yml           Auto-refresh job (8am, 4pm ET)
│   └── update-snapshot.yml             Manual-export trigger
├── README.md                           This file
└── ACTIONS-FOR-HANDOFF.md              Critical handoff items (read this)
```

No build step, no dependencies, no server-side code. Plain HTML + CSS +
JavaScript served as static files by GitHub Pages.

## Privacy

`<meta name="robots" content="noindex, nofollow">` is set on the dashboard so
search engines won't index it. The URL is unguessable enough that random
discovery is unlikely, but the data is operational ticket information, not
public-facing. Don't share the URL outside Neumo.

The repository is public (required for GitHub Pages on a free personal
account). This means anyone who happens upon the repo URL can see the
ticket data in `snapshots-*.json`. Mitigate by keeping the URL internal
and avoiding the inclusion of sensitive content in ticket summaries.

## Handoff

**Important:** before Mandy's transition completes, read
[`ACTIONS-FOR-HANDOFF.md`](./ACTIONS-FOR-HANDOFF.md). It covers the Jira
API token, repo ownership, and other items that will break the dashboard
if not addressed.

## Authored by

Mandy Miller, May 2026. Generalized June 2026.
