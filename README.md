[README.md](https://github.com/user-attachments/files/28555578/README.md)
# Records — Escalation & Delivery Dashboard

A live dashboard tracking escalation and delivery for one or more Records Suite
clusters. Originally built for the North Texas support spike (May 2026);
generalized for any escalation cluster.

**Live URL:** https://kofile.github.io/records-ntx-dashboard/

## What it shows (per active cluster)

Four tiles, each answering one question:

1. **Are we winning?** — Delivery rate, three-way split (delivered / pending / open), cumulative trend chart.
2. **What's committed and shipping** — Delivery target labels + production End Dates.
3. **Where's the bottleneck?** — Open tickets by stage, with aging.
4. **Customer pain** — Open count per tenant.

Plus a Customer Prep view for per-tenant client-safe summaries.

## Cluster registry (source of truth)

The list of active clusters lives in a **Confluence page**, not in this repo:

**[Records Dashboard — Active Clusters](https://neumo.atlassian.net/wiki/spaces/PRS/pages/3891593217/Records+Dashboard+Active+Clusters)**

To add a cluster: edit the Confluence page, add a row to the table, publish.
To remove a cluster: delete its row, publish. No GitHub access required.

The dashboard's "⚙ Manage clusters in Confluence" link in the cluster bar
opens this page directly.

## How the data flows

```
Confluence page (registry)
        │  read by GitHub Action
        ▼
GitHub Actions (2× business day: 8am, 4pm ET)
        │  for each cluster: fetch_jira_filter.py
        ▼
Jira API
        │
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

No human touches GitHub to add/remove clusters. The GitHub Action does it
all, under the existing `JIRA_TOKEN` secret.

## Refresh schedule

Auto-refresh runs **twice per business day** via GitHub Actions:
- **8:00 AM ET** (12:00 UTC)
- **4:00 PM ET** (20:00 UTC)

Monday through Friday only.

Cron schedule defined in [`.github/workflows/scheduled-refresh.yml`](./.github/workflows/scheduled-refresh.yml).

If the auto-refresh fails (e.g., expired API token, malformed registry page,
unreachable filter), an issue is automatically opened with a runbook.

## Resilience: registry fallback

If the Confluence registry page becomes unreachable (Atlassian outage,
permissions issue, page deleted), the workflow falls back to the existing
`clusters.json` file (last known good list). The dashboard continues to
serve the most recent data until the registry is reachable again.

## Repository structure

```
records-ntx-dashboard/
├── index.html                          The dashboard (single-page web app)
├── snapshots.json                      Aggregator file (entry point)
├── snapshots-29799.json                N TX cluster data
├── snapshots-<other-id>.json           One per registered cluster
├── clusters.json                       Cached cluster list (auto-generated; do NOT edit)
├── read_cluster_registry.py            Reads the Confluence registry page
├── fetch_jira_filter.py                Pulls one filter's data from Jira API
├── build_aggregator.py                 Rebuilds snapshots.json
├── update_snapshots.py                 Manual-export fallback (deprecated; default cluster only)
├── jira-exports/                       Manual HTML exports (backup workflow, deprecated)
├── .github/workflows/
│   ├── scheduled-refresh.yml           Auto-refresh job (8am, 4pm ET)
│   └── update-snapshot.yml             Manual-export trigger (DISABLED)
├── README.md                           This file
└── ACTIONS-FOR-HANDOFF.md              Critical handoff items (read this)
```

No build step, no dependencies, no server-side code. Plain HTML + CSS +
JavaScript served as static files by GitHub Pages.

## Privacy

`<meta name="robots" content="noindex, nofollow">` is set on the dashboard
so search engines won't index it. The URL is unguessable enough that
random discovery is unlikely, but the data is operational ticket
information, not public-facing. Don't share the URL outside Neumo.

The repository is currently public (required for GitHub Pages on a free
personal account). This means anyone who happens upon the repo URL can see
the ticket data in `snapshots-*.json`. Mitigate by keeping the URL
internal.

## Handoff

**Important:** before Mandy's transition completes, read
[`ACTIONS-FOR-HANDOFF.md`](./ACTIONS-FOR-HANDOFF.md). It covers the Jira
API token, repo ownership, and other items that will break the dashboard
if not addressed.

## Authored by

Mandy Miller, May 2026. Generalized June 2026.
