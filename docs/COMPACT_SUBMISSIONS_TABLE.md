# Compact submissions table (standard for all campaign submission pages)

`frontend/src/components/CompactSubmissionsTable.js` is the one table used for campaign
submissions on Telegizer (official + custom bots) and Guildizer (Discord).

## Use it for a new submissions page
1. Map your model to a row (an "adapter") - see `subRows` in `components/CampaignManager.js`
   (Telegram) and `pages/guildizer/tabs/CampaignsTab.js` (Discord):
   `{ id, userName, userId, taskTitle, proofUrl, proofText, proofExtra, status, xp, createdAt,
   flagged, flagReason, reviewedBy, reviewedAt, reviewReason, notifyStatus, notifyError, raw }`.
2. Render `<CompactSubmissionsTable rows showTask onApprove onReject renderDetail />`.
   `showTask` is false for single-task campaigns (Task column hidden). `renderDetail(row)` is the
   expandable panel - put anything campaign-specific there (custom fields, screenshots, per-action chips).
3. Do not add reviewer/notification lines to the row; they live in the status tooltip + detail panel.

Built in: sticky header, sort (user/task/status/XP/date), search, status + task filters,
25/50/100 pagination, approve confirmation, truncated task/proof with full value on hover.

## Google Sheets (`GoogleSheetsButton` + `utils/googleSheets.js`)
- Browser OAuth via Google Identity Services, `drive.file` scope only; token stays in memory.
- Writes the complete dataset the (permission-checked) backend returned, not the visible page.
- Linked sheet id is remembered per campaign in localStorage (`telegizer:sheet:<key>`) so reopening
  never duplicates; **Refresh Sheet** re-writes it. It is a **snapshot**, not live sync. Never public.
- Requirements: Sheets API enabled in the Google Cloud project; the site origin listed under
  "Authorized JavaScript origins" of the OAuth client; `GOOGLE_CLIENT_ID` set on the backend
  (served via `GET /api/calendar/client-id`) or `REACT_APP_GOOGLE_CLIENT_ID` on the frontend.
  While the OAuth consent screen is in "Testing", only listed test users can authorize.
