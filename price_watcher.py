import requests, re, csv, json, random, time
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

CONFIG_PATH = Path("config.json")

DATA_PATH = Path("price_history.csv")
if not DATA_PATH.exists():
    with open(DATA_PATH, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "query", "url", "price"])
        writer.writeheader()

# ----------------- Utils -----------------
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_price(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d[\d\s.,]*\s?€)", text)
    if not m:
        return None
    raw = m.group(1).replace("€", "").strip().replace(" ", "")
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except:
        return None

def ships_to_france(html):
    text = html.lower()
    keywords = [
        "livraison en france",
        "shipping to france",
        "expédition france",
        "livraison france",
        "ship to france",
        "available in france"
    ]
    return any(k in text for k in keywords)

def fetch_google_results(query, n=10):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.select("a"):
        href = a.get("href", "")
        if href.startswith("http") and "google" not in href:
            links.append(href)
        if len(links) >= n:
            break
    return links

def fetch_bing_results(query, n=10):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://www.bing.com/search?q={query.replace(' ', '+')}"
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.select("li.b_algo h2 a"):
        href = a.get("href", "")
        if href.startswith("http"):
            links.append(href)
        if len(links) >= n:
            break
    return links

def append_history(row):
    exists = DATA_PATH.exists()
    with open(DATA_PATH, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "query", "url", "price"])
        if not exists:
            writer.writeheader()
        writer.writerow(row)

def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

# ----------------- Main -----------------
def main():
    cfg = load_config()
    headers = {"User-Agent": "Mozilla/5.0"}
    for q in cfg["queries"]:
        print(f"🔎 Recherche: {q}")
        links = fetch_google_results(q, n=cfg["results_per_query"]) + fetch_bing_results(q, n=cfg["results_per_query"])
        for link in links:
            print(" →", link)
            try:
                html = requests.get(link, headers=headers, timeout=15).text
                if not ships_to_france(html):
                    print(" ❌ Ne livre pas en France, on ignore")
                    continue
                price = extract_price(html)
            except Exception as e:
                print("Erreur:", e)
                continue
            if price:
                append_history({
                    "date": datetime.utcnow().isoformat(),
                    "query": q,
                    "url": link,
                    "price": price
                })
                print(f"💰 Prix trouvé: {price}€ pour {link}")
                # alerte Telegram si prix inférieur au dernier
                try:
                    previous_prices = []
                    if DATA_PATH.exists():
                        with open(DATA_PATH, newline='', encoding='utf-8') as f:
                            for r in csv.DictReader(f):
                                if r["url"] == link:
                                    previous_prices.append(float(r["price"]))
                    if previous_prices and price < min(previous_prices):
                        msg = f"📉 Nouveau prix bas détecté: {price}€\n{link}"
                        send_telegram_message(cfg["telegram_bot_token"], cfg["telegram_chat_id"], msg)
                except:
                    pass
            time.sleep(random.uniform(2,5))

if __name__ == "__main__":
    main()
