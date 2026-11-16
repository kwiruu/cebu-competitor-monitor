# n8n workflows

**Status: drafts. Not yet imported or tested in n8n.**

| File | What it does |
|---|---|
| `competitor-changes.workflow.json` | Receives tickets from the scraper, adds each to the sheet, sends high-severity ones to Telegram with buttons, and reports scraper failures |
| `ticket-decisions.workflow.json` | When a button is pressed, writes the decision back to the ticket row |

## Google Sheet layout

Tab `Competitors` (row 1 is the header):

```
name | website | page_url | page_type | is_us | crawl_delay_s | active
```

Tab `Changes` (row 1 is the header; n8n fills the rows):

```
change_id | detected_at | competitor | offer | category | change_type | old_value | new_value | pct_change | severity | message | status | decision | decided_at
```

## Setup in n8n

1. Create three credentials: **Telegram** (bot token), **Google Service Account** (email and private key from the key file), and **Header Auth** (name `X-Monitor-Secret`, value the same as `N8N_WEBHOOK_SECRET`).
2. Import both files, then pick the credentials on each node.
3. Replace `PASTE_GOOGLE_SHEET_ID` and `PASTE_TELEGRAM_CHAT_ID`.
4. Activate both workflows and copy the webhook's production URL into `N8N_WEBHOOK_URL`.

## Test without waiting for a real price change

```bash
python scripts/send_sample_ticket.py
```

This posts one clearly labelled sample ticket (`change_id` 0) to the webhook. It does not touch the database.
