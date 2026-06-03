# Actions required before Mandy's transition

This document lists the things that will break the dashboard if not handled
before Mandy Miller's last day at Neumo.

**Read time: 5 minutes. Action time: ~30 minutes.**

---

## 🔴 Critical — will break the dashboard

### 1. Transfer the Jira API token

**Current state:** The scheduled refresh authenticates against Jira using
two GitHub repo secrets:
- `JIRA_USER` — set to Mandy's email (`mandy.miller@neumo.com`)
- `JIRA_TOKEN` — a personal API token Mandy generated in her Atlassian
  account
- `JIRA_HOST` — `neumo.atlassian.net`

**What will break:** When Mandy's Neumo account is deactivated, her Atlassian
account is deactivated with it, and her API token stops working. The next
scheduled refresh after deactivation fails with HTTP 401. The dashboard
continues showing the last successful snapshot but stops updating.

**What to do:**

1. **Pick a successor token holder.** Best practice is a non-personal "bot"
   account (e.g., `records-dashboard-bot@neumo.com`). If no bot account
   exists, a long-tenure team member can use their personal account —
   recommend Tamara Woodward as the primary candidate (she's already named
   as triage owner across several systems and has Jira access).
2. **The token holder generates a Jira API token:**
   `https://id.atlassian.com/manage-profile/security/api-tokens` → "Create
   API token" → label it "records-dashboard". Copy the token *immediately*
   (it's not shown again).
3. **Verify the token holder has read access to every filter listed in
   `clusters.json`.** Open each filter URL in Jira; if any return "no
   permission", that filter's owner needs to share it with the new token
   holder.
4. **Update the GitHub repo secrets:**
   - Go to `Settings → Secrets and variables → Actions`
   - Click `JIRA_USER` → "Update" → enter the new email
   - Click `JIRA_TOKEN` → "Update" → paste the new token
5. **Trigger a manual run to verify:** Actions tab → "Scheduled dashboard
   refresh" → "Run workflow". Should complete green within 60 seconds.

---

### 2. Transfer GitHub repo ownership

**Current state:** The repository sits on Mandy's personal GitHub account.
GitHub Pages on a free personal account requires the repo to be public,
which it is. Mandy's account is the only one with admin rights.

**What will break:** When Mandy leaves Neumo and eventually deletes or
archives her personal GitHub account, the repo and the live URL disappear.
Even before that, only Mandy can rotate the API token, change the schedule,
or fix a failing workflow.

**What to do — pick one of three paths:**

**Path A (recommended): Transfer the repo into a Kofile/Neumo GitHub
organization.**
- Requires the org to have GitHub Enterprise Cloud (or be willing to enable
  it). Confirm with Christopher Burch (DevOps) whether Neumo has Enterprise
  Cloud.
- If yes: Settings → "Transfer ownership" → enter the org name. Pages
  configuration carries over. The dashboard URL changes to
  `https://<org>.github.io/records-ntx-spike/` (existing bookmarks need
  updating).
- After transfer, give Tamara Woodward and at least one DevOps person
  admin access.

**Path B: Transfer the repo to a successor's personal account.**
- Simpler, no IT involvement.
- Less durable — the next successor faces the same problem.
- Successor must have a GitHub account and accept the transfer.

**Path C: Move to a different host.**
- Migrate the dashboard to Azure Static Web Apps (David has experience
  here). Requires re-wiring the auto-refresh — Azure SWA doesn't run cron
  jobs natively, so the GitHub Actions in this repo would need to push
  builds to Azure on every refresh, or the refresh logic moves to an
  Azure Function.
- Most rebuild work; probably not worth it for the spike's remaining life.

---

### 3. Confirm the manual backup workflow still works for non-N TX clusters

**Current state:** `update_snapshots.py` and `update-snapshot.yml` were
written for the single-cluster N TX dashboard. They process Jira HTML
exports and write to `snapshots.json` (the legacy format).

**What's incomplete:** When this dashboard was generalized, the
auto-refresh path (`fetch_jira_filter.py`) was updated to handle multiple
clusters. The manual fallback path was *not*. If the auto-refresh breaks
and the team needs to manually refresh Wayne, Cuyahoga, etc., there's no
direct path.

**What to do (low priority — only matters if auto-refresh breaks):**

For now, the manual path works only for the default cluster (N TX). If a
non-default cluster needs a manual refresh:
1. Run `update_snapshots.py` locally pointing the output at
   `snapshots-<filter_id>.json`
2. Run `build_aggregator.py` to refresh `snapshots.json`
3. Commit both files

A future cleanup task: refactor `update_snapshots.py` to take a
`--filter-id` argument and to write to the per-cluster file directly,
matching the pattern in `fetch_jira_filter.py`.

---

## 🟡 Worth addressing — won't break the dashboard but creates risk

### 4. Document who holds the URL

The dashboard URL has been shared with the NTX support team and likely
some execs. It is not in any directory or wiki. When the URL changes (if
the repo moves under Path A above), anyone holding the old bookmark gets a
dead link.

**What to do:** Make a list of people who use the dashboard. Tamara,
Gargee, Joy, Sandy, RB at minimum. When the URL changes, send them the
new one in one Slack message.

### 5. The repo's git history contains real ticket data

Every snapshot commit since the repo started has live ticket data —
summaries, tenants, statuses. Anyone reading the public repo history can
read months of Neumo's operational pain points. This is not new; it has
been true since launch. But it's worth being aware of.

**What to do:** If at any point the repo moves private (e.g., Path A
above), the history travels with it and stops being publicly readable.
Until then, nothing to do — the data already exists publicly.

### 6. Add a successor as a `CODEOWNERS` reviewer

Create `.github/CODEOWNERS` listing the successor team's GitHub usernames.
Every change to `clusters.json`, the workflow files, or `index.html` will
require their review. This protects against accidental changes after
Mandy leaves.

---

## Quick checklist

Items 1, 2, 3 are the only ones that break the dashboard. The others are
hygiene.

- [ ] **1. Jira API token** transferred to a successor account. New
      `JIRA_USER` and `JIRA_TOKEN` secrets set. Manual run verifies green.
- [ ] **2. Repo ownership** transferred (Path A, B, or C chosen and
      executed).
- [ ] **3. Manual backup workflow** documented or refactored.
- [ ] **4. URL recipient list** assembled.
- [ ] **5. Awareness** of public-history data exposure logged.
- [ ] **6. CODEOWNERS** file added.

---

## Questions

Authored by Mandy Miller (mandy.miller@neumo.com), June 2026, before
transition. Updated as items are completed.
