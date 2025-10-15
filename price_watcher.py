# price_watcher.py
import requests, re, csv, json, random, time
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

CONFIG_PATH = Path("config.json")
DATA_PATH = Path("price_history.csv")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_google_results(query, n=5):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.select("a"):
        href = a.get("href", "")
        if href.startswith("http") and "google" not in href:
            links.append(href)
        if len(links) >= n:
            break
    return links

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

def load_history():
    if not DATA_PATH.exists():
        return {}
    data = {}
    with open(DATA_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            data.setdefault(r["url"], []).append(float(r["price"]))
    return data

def append_history(row):
    exists = DATA_PATH.exists()
    with open(DATA_PATH, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "query", "url", "price"])
        if not exists:
            writer.writeheader()
        writer.writerow(row)

def main():
    cfg = load_config()
    history = load_history()
    headers = {"User-Agent": "Mozilla/5.0"}
    for q in cfg["queries"]:
        print(f"🔎 Recherche: {q}")
        for link in fetch_google_results(q, n=cfg["results_per_query"]):
            print(" →", link)
            try:
                html = requests.get(link, headers=headers, timeout=15).text
                price = extract_price(html)
            except Exception as e:
                print("Erreur:", e)
                continue
            if price:
                append_history({
                    "date": datetime.utcnow().isoformat(),
                    "query": q,
                    "url": link,
                    "price": price,
                })
                last_prices = history.get(link, [])
                if last_prices and price < min(last_prices):
                    print(f"💰 Nouveau prix bas détecté: {price}€ pour {link}")
            time.sleep(random.uniform(2, 5))

if __name__ == "__main__":
    main()
