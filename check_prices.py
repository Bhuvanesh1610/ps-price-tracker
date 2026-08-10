"""
PS Store Wishlist Price Checker
--------------------------------
Reads game URLs from games.txt, fetches the current price for each from
the PS Store, and sends a Telegram alert for any game that:
  - has a discounted price below RS_THRESHOLD, OR
  - has a discount percentage >= DISCOUNT_THRESHOLD

Run manually with:  python check_prices.py
Requires env vars:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import os
import re
import html
import sys
import time
import requests
from bs4 import BeautifulSoup

RS_THRESHOLD = 1000          # alert if discounted price is below this (INR)
DISCOUNT_THRESHOLD = 50      # alert if discount percentage is >= this
GAMES_FILE = "games.txt"
REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


def load_urls(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def parse_price_string(value):
    """Convert '₹2,499' / 'Rs 2,499' / 2499 -> 2499.0 (float). Returns None if not parseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def get_title(soup):
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.replace(" | PlayStation Store", "").strip()
    return "Unknown Game"


def fetch_game_info(url):
    """Returns dict with title/base/discounted/discount_pct, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Fetch failed for {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title = get_title(soup)

    # PS Store renders one of two patterns in the page text for the main
    # product's price block:
    #   Discounted:      "Discounted from original price of Rs 4,999 Rs 2,499"
    #   Not discounted:  "Rs 2,499"  (just one price, no "original price of" text)
    page_text = soup.get_text(separator=" ", strip=True)

    base = discounted = None

    m = re.search(
        r"Discounted from original price of\s*(?:Rs\.?|₹)\s?([\d,]+)\s*(?:Rs\.?|₹)\s?([\d,]+)",
        page_text,
    )
    if m:
        base = parse_price_string(m.group(1))
        discounted = parse_price_string(m.group(2))
    else:
        # Not on sale (or free/subscription-only) - grab the first plain price
        m2 = re.search(r"(?:Rs\.?|₹)\s?([\d,]+)", page_text)
        if m2:
            discounted = parse_price_string(m2.group(1))
            base = discounted

    if discounted is None:
        print(f"[ERROR] Could not extract price for {url}")
        return None

    if base is None or base <= 0:
        base = discounted

    discount_pct = round((1 - (discounted / base)) * 100) if base > 0 else 0

    return {
        "url": url,
        "title": title,
        "base": base,
        "discounted": discounted,
        "discount_pct": discount_pct,
    }


def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[ERROR] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            api_url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False


def format_deal_line(info):
    # Escape title for Telegram's HTML parse_mode - unescaped "&", "<", ">"
    # (e.g. titles like "PS4 & PS5") cause Telegram to reject the whole message.
    safe_title = html.escape(info["title"])
    return (
        f"🎮 <b>{safe_title}</b>\n"
        f"   Actual: ₹{info['base']:,.0f}  |  Now: ₹{info['discounted']:,.0f}  "
        f"({info['discount_pct']}% off)\n"
        f"   {info['url']}"
    )


def main():
    urls = load_urls(GAMES_FILE)
    print(f"Checking {len(urls)} games...")

    deals = []
    failures = []

    for i, url in enumerate(urls, 1):
        info = fetch_game_info(url)
        if info is None:
            failures.append(url)
        else:
            hit_price = info["discounted"] < RS_THRESHOLD
            hit_discount = info["discount_pct"] >= DISCOUNT_THRESHOLD
            if hit_price or hit_discount:
                deals.append(info)
            print(
                f"[{i}/{len(urls)}] {info['title']}: "
                f"₹{info['discounted']:.0f} ({info['discount_pct']}% off) "
                f"{'-> ALERT' if (hit_price or hit_discount) else ''}"
            )
        time.sleep(1)  # be polite to the PS Store server

    if deals:
        lines = [f"🔥 <b>{len(deals)} wishlist game(s) hit your price alert!</b>\n"]
        lines += [format_deal_line(d) for d in deals]
        message = "\n\n".join(lines)
        # Telegram messages cap at 4096 chars; split if needed
        for chunk_start in range(0, len(message), 4000):
            send_telegram_message(message[chunk_start:chunk_start + 4000])
    else:
        print("No deals found this run.")

    # If every single game failed to parse, the site structure likely changed - flag it
    if failures and len(failures) == len(urls):
        send_telegram_message(
            "⚠️ PS Store price checker: ALL games failed to fetch this run. "
            "The script may need updating (PS Store page structure may have changed)."
        )

    if failures:
        print(f"\n{len(failures)} game(s) failed to fetch:")
        for f in failures:
            print(f"  - {f}")


if __name__ == "__main__":
    sys.exit(main())
