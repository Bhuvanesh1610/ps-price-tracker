"""
PS Store Wishlist Price Checker
--------------------------------
Reads game URLs from games.txt or the wishlist API, fetches prices from
PlayStation Store, Flipkart, or Amazon, and sends a Telegram alert for any game that:
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
from urllib.parse import urlparse
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


def load_games(path):
    wishlist_api_url = os.environ.get("WISHLIST_API_URL")
    if wishlist_api_url:
        try:
            response = requests.get(wishlist_api_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            games = response.json().get("games", [])
            games = [game for game in games if game.get("url")]
            print(f"Loaded {len(games)} active games from wishlist API.")
            return games
        except (requests.RequestException, ValueError, TypeError, KeyError) as e:
            print(f"[ERROR] Wishlist API fetch failed: {e}")
            return []

    with open(path, "r", encoding="utf-8") as f:
        return [{"url": line.strip(), "source": "playstation"} for line in f if line.strip() and not line.startswith("#")]


def source_for_url(url):
    host = urlparse(url).netloc.lower()
    if "flipkart.com" in host:
        return "flipkart"
    if "amazon." in host:
        return "amazon"
    return "playstation"


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


def fetch_game_info(game):
    """Return title, source, prices, and evidence URL, or None on failure."""
    url = game["url"]
    source = game.get("source") or source_for_url(url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Fetch failed for {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title = get_title(soup)

    if source in ("flipkart", "amazon"):
        prices = []
        for selector in ('meta[property="product:price:amount"]', 'meta[itemprop="price"]'):
            element = soup.select_one(selector)
            if element and element.get("content"):
                prices.append(parse_price_string(element["content"]))
        page_text = soup.get_text(separator=" ", strip=True)
        matches = re.findall(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)", page_text, re.I)
        prices.extend(parse_price_string(value) for value in matches)
        prices = [price for price in prices if price is not None]
        if not prices:
            print(f"[ERROR] Could not extract {source} price for {url}")
            return None
        discounted = prices[0]
        base = prices[1] if len(prices) > 1 and prices[1] >= discounted else discounted
        return {"url": url, "title": title, "source": source, "base": base,
                "discounted": discounted, "discount_pct": round((1 - discounted / base) * 100) if base else 0}

    page_text = soup.get_text(separator=" ", strip=True)

    # Scope the search to the MAIN product's own price block, starting at its
    # title and ending before the "Editions:" section. Without this, a price
    # or discount belonging to a different edition/add-on further down the
    # same page can get picked up by mistake.
    h1 = soup.find("h1")
    anchor = h1.get_text(strip=True) if h1 else title
    start_idx = page_text.find(anchor) if anchor else -1
    if start_idx == -1:
        start_idx = 0
    end_idx = page_text.find("Editions:", start_idx)
    if end_idx == -1 or end_idx <= start_idx:
        end_idx = start_idx + 2000
    window = page_text[start_idx:end_idx]

    base = discounted = None

    # Discounted case: "Rs 973 Discounted from original price of Rs 3,246 Rs 3,246"
    # -> discounted price appears BEFORE the phrase, original price AFTER it.
    # (Whitespace between the price and the phrase varies, so \s* handles both.)
    m = re.search(
        r"(?:Rs\.?|₹)\s?([\d,]+)\s*Discounted from original price of\s*(?:Rs\.?|₹)\s?([\d,]+)",
        window,
    )
    if m:
        discounted = parse_price_string(m.group(1))
        base = parse_price_string(m.group(2))
    else:
        # Not on sale - just a single plain price shown, e.g. "Rs 2,499"
        m2 = re.search(r"(?:Rs\.?|₹)\s?([\d,]+)", window)
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
        "source": source,
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
        f"   Source: <b>{html.escape(info['source'].title())}</b>\n"
        f"   Actual: ₹{info['base']:,.0f}  |  Now: ₹{info['discounted']:,.0f}  "
        f"({info['discount_pct']}% off)\n"
        f"   {info['url']}"
    )


def main():
    games = load_games(GAMES_FILE)
    print(f"Checking {len(games)} games...")

    deals = []
    failures = []

    for i, game in enumerate(games, 1):
        info = fetch_game_info(game)
        if info is None:
            failures.append(game["url"])
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
    if failures and len(failures) == len(games):
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
