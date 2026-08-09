# PS Store Wishlist Price Tracker

Checks your PS Store wishlist games twice a day (9 AM & 5 PM IST) and sends you
a Telegram message when a game:
- drops below **₹1000**, OR
- has a discount of **50% or more**

Runs entirely for free on GitHub Actions — no server, no laptop needed.

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

Add or remove PS Store product links in `games.txt`, one per line. Get a
link by opening the game's PS Store page and copying the URL — it should
look like:
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
