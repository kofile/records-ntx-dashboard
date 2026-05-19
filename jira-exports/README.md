# Jira exports folder

This folder is where you upload daily Jira HTML exports.

## How it works

1. Export Jira filter #29799 as HTML (top-right of the issue list: Export → HTML)
2. Save the file to your Mac
3. Upload it here via GitHub's web UI:
   - Click "Add file" → "Upload files"
   - Drag the file into this folder
   - Click "Commit changes"
4. A GitHub Action automatically runs in the background:
   - Parses the file
   - Updates `snapshots.json` at the repo root
   - The dashboard URL shows the new data within ~2 minutes

You don't need to run anything on your Mac. You don't need Python. You don't
need the command line. Just drag, drop, and commit.

## Filename convention (optional)

The Action auto-detects the snapshot date from the Jira HTML itself. So any
filename works. But if you want to be tidy, this convention is nice:

```
jira_2026-05-20.html
jira_2026-05-21.html
jira_2026-05-22.html
```

It keeps the folder sorted by date in GitHub's file listing.

## Backfills

If you missed a day, just upload the older export. The Action figures out the
right date from the file and slots it into the dashboard's trend chart in
the correct position — the "current snapshot" on the dashboard stays as the
most recent date.

## Audit trail

Files in this folder are kept indefinitely. If anyone asks "what did the
dashboard look like on May 20?", the original Jira export from that day is
right here.

## Troubleshooting

- **Uploaded a file, dashboard didn't update?** Check the Actions tab at
  `https://github.com/<your-username>/records-ntx-spike/actions`. If the
  workflow failed, the error message will tell you why.
- **Wrong date showed up?** The Action parses the date from the Jira HTML's
  "Displaying N issues at..." line. If the date is wrong, the Jira export's
  timestamp is wrong — re-export from Jira.
