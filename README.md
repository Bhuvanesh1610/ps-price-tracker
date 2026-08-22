# PS Store Wishlist Price Tracker

Checks your PS Store wishlist games twice a day (9 AM & 5 PM IST) and sends you
a Telegram message when a game:
- drops below **₹1000**, OR
- has a discount of **50% or more**

Runs entirely for free on GitHub Actions — no server, no laptop needed.

## Cloudflare wishlist site

The repository now includes a small Cloudflare Worker + D1 (SQLite) app. It
provides a browser page to view, add, and remove wishlist games. D1's free
tier is enough for this small list, and the scheduled runner reads the live
list from the API on every CI run.

### One-time Cloudflare setup

1. Install Wrangler and log in:
   ```
   npm.cmd install -g wrangler
   wrangler.cmd login
   ```
2. Create the free D1 database:
   ```
   wrangler.cmd d1 create ps-price-tracker
   ```
3. Copy the returned `database_id` into `wrangler.toml`, replacing
   `REPLACE_WITH_D1_DATABASE_ID`.
4. Set a private admin token locally:
   ```
   wrangler.cmd secret put ADMIN_TOKEN
   ```
5. Apply the schema and deploy once:
   ```
   wrangler.cmd d1 migrations apply ps-price-tracker --remote
   wrangler.cmd deploy
   ```

On Windows PowerShell, use the `.cmd` suffix because the system execution
policy may block `npm.ps1` and `npx.ps1`. The repository also includes
`npm.cmd run dev`, `npm.cmd run migrate`, and `npm.cmd run deploy` scripts.

The deployment URL printed by Wrangler is the wishlist page. The page asks
for `ADMIN_TOKEN` only when adding or removing games. A GET of `/api/games` is
public so GitHub Actions can read it without exposing a write credential.

### GitHub Actions secrets

Add these under **Settings -> Secrets and variables -> Actions**:

| Name | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Workers edit and D1 edit permissions |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `ADMIN_TOKEN` | The same token used by the wishlist page |
| `WISHLIST_API_URL` | Deployment URL followed by `/api/games` |

Pushes to `main` run `.github/workflows/deploy.yml`. The deploy job applies
new D1 migrations, updates the Worker secret, and publishes the site. The
existing `check-prices.yml` schedule then reads games added through the page.

## 1. Create the GitHub repo

1. Go to [github.com/new](https://github.com/new), create a **private** repo
   (e.g. `ps-price-tracker`).
2. Upload all the files in this folder, keeping the folder structure:
   ```
   ps-price-tracker/
   ├── .github/workflows/check-prices.yml
   ├── check_prices.py
   ├── games.txt
   ├── requirements.txt
   └── README.md
   ```
   Easiest way: on the repo page, click **Add file → Upload files**, drag
   everything in (GitHub preserves the `.github/workflows/` path automatically
   if you drag the whole folder, or create the file manually if it doesn't).

## 2. Add your Telegram credentials as Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add two secrets:
| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | your chat ID from @userinfobot |

Never put these directly in the code or games.txt — Secrets keep them encrypted.

## 3. Test it manually

1. Go to the **Actions** tab in your repo.
2. Click **Check PS Store Prices** on the left.
3. Click **Run workflow → Run workflow** (this is the `workflow_dispatch`
   trigger — lets you test without waiting for 9 AM/5 PM).
4. After ~1-2 minutes, click into the run to see the logs — it'll show the
   price it found for every game. If your Telegram is set up correctly and
   any game qualifies, you'll get a message.

## 4. Let it run automatically

Nothing else to do — the workflow in `.github/workflows/check-prices.yml` is
already scheduled for 9:00 AM and 5:00 PM IST daily. GitHub Actions runs it
for you as long as the repo has had *some* activity in the last 60 days
(private repos with scheduled workflows can get auto-disabled after long
inactivity — just re-run it manually if that happens).

## Managing your game list

Use the deployed wishlist page to add games or remove games you have bought.
The runner reads that live D1 list whenever the scheduled or manual workflow
starts. For local runs without `WISHLIST_API_URL`, the runner still reads
`games.txt`. A PS Store URL should look like:
```
https://store.playstation.com/en-in/product/EP0102-PPSA01557_00-VILLAGEFULLGAMEX
```

## Adjusting the thresholds

Open `check_prices.py` and change these two lines near the top:
```python
RS_THRESHOLD = 1000          # alert if price drops below this
DISCOUNT_THRESHOLD = 50      # alert if discount % is at least this
```

## If it stops working

PS Store occasionally changes its page structure, which can break the price
scraper. If that happens:
- Check the **Actions** tab logs — the script logs a `[ERROR]` line for any
  game it couldn't parse.
- If literally *every* game fails in one run, the script sends you a
  one-time Telegram warning saying it may need updating.
