[ACTIONS-FOR-HANDOFF.md](https://github.com/user-attachments/files/28555592/ACTIONS-FOR-HANDOFF.md)
# Actions required before Mandy's transition

This document lists the things that will break the dashboard if not handled
before Mandy Miller's last day at Neumo.

**Read time: 5 minutes. Action time: ~45 minutes.**

---

## 🔴 Critical — will break the dashboard

### 1. Transfer the Atlassian API token

**Current state:** The scheduled refresh authenticates against Atlassian
(both Jira and Confluence) using two GitHub repo secrets:
- `JIRA_USER` — currently Mandy's email (`mandy.miller@neumo.com`)
- `JIRA_TOKEN` — a personal API token Mandy generated in her Atlassian account
- `JIRA_HOST` — `neumo.atlassian.net`

(The `JIRA_*` naming is historical — the same token also authenticates
to Confluence, since both are under the Atlassian Cloud umbrella.)

**What will break:** When Mandy's Neumo account is deactivated, her
Atlassian account is deactivated with it, and the API token stops working.
The next scheduled refresh after deactivation fails with HTTP 401. The
dashboard continues showing the last successful snapshot but stops
updating. **The Confluence registry page also becomes unreachable to the
workflow** until the credentials are updated.

**What to do:**

1. **Confirm the successor.** As of June 2026, the planned successor is
   **Gargee Kar** (Support). Verify with Sandy Oliver and Joy Johnson
   before transferring credentials.
2. **The successor generates an Atlassian API token:**
   `https://id.atlassian.com/manage-profile/security/api-tokens` →
   "Create API token" → label it "records-dashboard". Copy the token
   immediately (it's not shown again).
3. **Verify the successor has access to:**
   - The Confluence registry page at
     `https://neumo.atlassian.net/wiki/spaces/PRS/pages/3891593217`
   - Every Jira filter currently listed on the registry page
   - (As filters get added, the successor needs read access to each one;
     this is documented in the registry page's "How to add a cluster" section)
4. **Update the GitHub repo secrets:**
   - Go to `Settings → Secrets and variables → Actions`
   - Click `JIRA_USER` → "Update" → enter the new email
   - Click `JIRA_TOKEN` → "Update" → paste the new token
5. **Update the Confluence registry page's "Service account" section** to
   reflect the new account email (so future operators know what to do
   when this needs to happen again).
6. **Trigger a manual run to verify:** Actions tab → "Scheduled dashboard
   refresh" → "Run workflow". Should complete green within ~60 seconds.

---

### 2. Transfer GitHub repo ownership

**Current state:** The repository sits on Kofile's organization GitHub
account (`github.com/kofile/records-ntx-dashboard`). Mandy has admin
rights along with whoever else has org-level access.

**What might break:** If Mandy is the only person with repo-level admin
rights, her departure removes the ability to rotate secrets, fix workflow
failures, or change settings. This depends on Kofile's org-level access
policies — if other org members can administer this repo by default, no
action needed.

**What to do:**

1. Confirm with IT / DevOps (Christopher Burch is the named contact) that
   at least one other person has full admin rights on the repo *before*
   Mandy's account is deactivated.
2. Suggested additions: Tamara Woodward (delivery lead), Gargee Kar (the
   successor for daily operations), and one DevOps person.

---

### 3. Decide what to do with `update_snapshots.py` and the manual workflow

**Current state:** The repo still contains `update_snapshots.py` and
`.github/workflows/update-snapshot.yml`. These powered the original manual
backup workflow (drag a Jira HTML export into `jira-exports/`, dashboard
updates). Both are now **disabled** because they write to the old single-
file `snapshots.json` format and would corrupt the multi-cluster
aggregator if they ran.

**What to do (low priority — only matters if auto-refresh breaks):**

Two options:
- **A — Remove them.** The auto-refresh is the only data path; remove the
  manual workflow entirely. Cleaner repo.
- **B — Refactor them.** Update `update_snapshots.py` to accept a
  `--filter-id` argument and write to `snapshots-<filter_id>.json`. Keep
  as a true backup path.

Recommend A for simplicity, but defer the decision until the auto-refresh
has run cleanly for a few weeks and we know we don't need the backup.

---

## 🟡 Worth addressing — won't break the dashboard but creates risk

### 4. Document who holds the URL

The dashboard URL has been shared with the NTX support team and likely
some execs. When the URL changes (e.g., if the repo moves), anyone
holding the old bookmark gets a dead link.

**What to do:** Make a list of people who use the dashboard (Tamara,
Gargee, Joy, Sandy, RB at minimum). Use that list as a notification
channel for any future URL changes.

### 5. The repo's git history contains real ticket data

Every snapshot commit since the repo started has live ticket data —
summaries, tenants, statuses. Anyone reading the public repo history can
read months of Neumo's operational pain points. This is not new; it has
been true since launch.

**What to do:** No immediate action. If the repo moves into a private
GitHub org (e.g., GitHub Enterprise Cloud), the history travels with it
and stops being publicly readable.

### 6. Add a successor as a `CODEOWNERS` reviewer

Create `.github/CODEOWNERS` listing the successor team's GitHub usernames.
Every change to the workflow files or `index.html` will require their
review. Protects against accidental changes after Mandy leaves.

### 7. Confluence page permissions

The registry page lives in the PRS Confluence space. Anyone with edit
access to PRS can add or remove clusters. Verify the access list:
- **Add:** Tamara Woodward, Gargee Kar, and Mandy's successor for product
  ownership (whoever that ends up being).
- **Maintain visibility:** This page should be visible (read access) to
  the Records Suite team broadly — it's also documentation about what the
  dashboard tracks.

---

## Quick checklist

Items 1 and 2 are the only ones that hard-break the dashboard. The
others are hygiene.

- [ ] **1. Atlassian API token** transferred to a successor account. New
      `JIRA_USER` and `JIRA_TOKEN` secrets set. Confluence "Service
      account" section on the registry page updated. Manual run verifies
      green.
- [ ] **2. Repo admin access** confirmed for at least one non-Mandy person.
- [ ] **3.** Decide what to do with `update_snapshots.py` (defer).
- [ ] **4.** URL recipient list assembled.
- [ ] **5.** Awareness of public-history data exposure logged.
- [ ] **6.** `CODEOWNERS` file added.
- [ ] **7.** Confluence page permissions verified.

---

## Questions

Authored by Mandy Miller (mandy.miller@neumo.com), June 2026, before
transition. Updated as items are completed.
