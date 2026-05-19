# Records NTX Support Spike — Daily Dashboard

A daily-refreshed dashboard tracking the North Texas support spike at Neumo.

**Live URL:** `https://<your-username>.github.io/records-ntx-spike/`
*(replace with your actual GitHub Pages URL once deployed)*

## What it shows

Five tiles, each answering one question:

1. **Are we winning?** — Delivery rate, three-way split (delivered / pending / open), cumulative trend chart.
2. **What's committed and shipping** — Delivery target labels + production End Dates.
3. **Where's the bottleneck?** — Open tickets by stage, with aging.
4. **Customer pain** — Open count per NTX-5 county.
5. **Jira vs. Consolidated list** — Transitional divergence panel.

Plus a Customer Prep view for per-county client-safe summaries.

## How the data flows

```
Jira filter #29799  →  Daily HTML export  →  update_snapshots.py  →  snapshots.json  →  Dashboard renders
```

`snapshots.json` is the source of truth. The dashboard fetches it on page load.

## Daily refresh

Operator: Gargee Kar (Support). See `OPERATIONS.md` (forthcoming) for the
detailed daily workflow.

The short version:
1. Export Jira filter #29799 as HTML.
2. Run `update_snapshots.py <jira_export.html> snapshots.json` to update.
3. Push the updated `snapshots.json` to this repo.
4. GitHub Pages auto-publishes within ~1-2 minutes.

## Repository structure

```
records-ntx-spike/
├── index.html          The dashboard (single-page web app)
├── snapshots.json      The data (refreshed daily)
├── update_snapshots.py Utility to update snapshots.json from Jira HTML
├── README.md           This file
└── .gitignore
```

No build step, no dependencies, no server-side code. Plain HTML + CSS +
JavaScript served as static files by GitHub Pages.

## Privacy

`<meta name="robots" content="noindex, nofollow">` is set on the dashboard so
search engines won't index it. The URL is unguessable enough that random
discovery is unlikely, but the data is operational ticket information, not
public-facing. Don't share the URL outside Neumo.

This dashboard will be retired by end of July 2026.

## Authored by

Mandy Miller (mandy.miller@neumo.com), May 2026.
