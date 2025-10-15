# monitor.py
import os, json, re, time
from decimal import Decimal
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")

PRODUCTS_FILE = "products.json"
HISTORY_FILE = "history.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=20)
        print("Telegram:", r.status_code)
    except Exception as e:
        print("Telegram error:", e)

def parse_price_from_text(text):
    # retire les espaces/€/, et récupère le premier nombre
    # supporte 1 234,56 et 1234.56
    t = text.strip()
    # unify comma as decimal if format like 1 234,56
    # remove non-numeric except .,,
    t = re.sub(r"[^\d,.\-]", "", t)
    if t.count(",") and t.count(".") == 0:
        t = t.replace(",", ".")
    # keep first match like -?digits(.digits)
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        return Decimal(m.group(0))
    except:
        return None

def fetch_price_requests(url, css_selector=None, xpath=None):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print("HTTP", r.status_code, url)
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        if css_selector:
            el = soup.select_one(css_selector)
            if el:
                txt = el.get("content") or el.get_text()
                return parse_price_from_text(txt)
        # fallback: common meta tags
        meta = soup.find("meta", {"itemprop":"price"})
        if meta and meta.get("content"):
            return parse_price_from_text(meta["content"])
        # fallback: find any price-like text
        text = soup.get_text()
        m = re.search(r"[0-9]{1,3}(?:[ \.,][0-9]{3})*(?:[,\.][0-9]{2})?\s?€", text)
        if m:
            return parse_price_from_text(m.group(0))
        # last resort: first number on page
        return parse_price_from_text(text[:5000])
    except Exception as e:
        print("fetch error", e)
        return None

def main():
    products = json.loads(Path(PRODUCTS_FILE).read_text(encoding="utf-8"))
    history_path = Path(HISTORY_FILE)
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {}

    alerts = []
    for p in products:
        url = p["url"]
        css = p.get("price_selector_css")
        xpath = p.get("price_selector_xpath")
        print("Checking", p["name"], url)
        price = fetch_price_requests(url, css_selector=css, xpath=xpath)
        if price is None:
            print("Could not parse price for", p["name"])
            continue
        price_f = float(price)
        pid = p["id"]
        prev = history.get(pid, {})
        prev_price = prev.get("price")
        history.setdefault(pid, {})
        history[pid]["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        history[pid]["price"] = price_f
        history[pid]["url"] = url

        # detect change
        if prev_price is None:
            history[pid]["min_price"] = price_f
            history[pid]["max_price"] = price_f
            print("Initial price stored.")
        else:
            if price_f < prev_price:
                pct = (prev_price - price_f) / prev_price * 100
                threshold = p.get("threshold_percent", 0)
                if pct >= threshold:
                    msg = f"💸 *{p['name']}* price dropped: {prev_price:.2f} → {price_f:.2f} {p.get('currency','')}\n{url}\n-{pct:.1f}%"
                    alerts.append(msg)
            # update min/max
            if price_f < history[pid].get("min_price", price_f):
                history[pid]["min_price"] = price_f
            if price_f > history[pid].get("max_price", price_f):
                history[pid]["max_price"] = price_f

    # save history
    history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    # send alerts
    if alerts:
        full = "\n\n".join(alerts)
        print("Sending alerts")
        send_telegram(full)
        # also create a summary file for GitHub Actions to pick up or create an issue (workflow can create issue)
    else:
        print("No alerts.")

if __name__ == "__main__":
    main()
