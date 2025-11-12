import os
import re
import time
import random
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup

# Optional Selenium import (used only for fallback)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================
# 🔧 CONFIGURATION
# ==============================================================

GOOGLE_API_KEY = "AIzaSyCOnc1cUHkUJ_cMIH2IAXvKGQ8mbtXD0B8"
GOOGLE_CX = "f24bd79a3178d43f3"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}

# ==============================================================
# 🔧 UTILITIES
# ==============================================================

def tnap():
    time.sleep(random.uniform(0.8, 1.5))

def extract_asin(url):
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/gp/aw/d/([A-Z0-9]{10})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ==============================================================
# 🔍 GOOGLE SEARCH
# ==============================================================

def google_search(q, limit=10):
    base = "https://www.googleapis.com/customsearch/v1"
    results = []
    start = 1

    while len(results) < limit:
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CX,
            "q": q,
            "num": min(10, limit - len(results)),
            "gl": "ca",
            "hl": "en",
            "fields": "items(link,title)",
        }
        try:
            resp = requests.get(base, params=params, timeout=15)
            data = resp.json()
            items = data.get("items", [])
            for it in items:
                link = it.get("link", "")
                title = it.get("title", "")
                if "amazon.ca" in link:
                    results.append({
                        "asin": extract_asin(link),
                        "title": title,
                        "url": link,
                        "price": "",
                        "source": "google"
                    })
            if not items:
                break
        except Exception as e:
            print("❌ Google error:", e)
            break
        start += 10
        tnap()

    return results

# ==============================================================
# 🧠 SELENIUM FALLBACK
# ==============================================================

def selenium_amazon_search(q, max_pages=3):
    """
    Fallback when Google returns no results.
    Uses Selenium to directly scrape Amazon.ca search results.
    """
    print(f"⚙️ Launching Selenium for '{q}'...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-CA")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    all_results = []
    seen_asins = set()

    try:
        for page in range(1, max_pages + 1):
            search_url = f"https://www.amazon.ca/s?k={quote(q)}&page={page}"
            driver.get(search_url)
            time.sleep(random.uniform(2, 3))

            product_elems = driver.find_elements(By.CSS_SELECTOR, "div.s-result-item[data-asin]")
            if not product_elems:
                print(f"⚠️ No items found on page {page}")
                break

            for item in product_elems:
                asin = item.get_attribute("data-asin")
                if not asin or asin in seen_asins:
                    continue
                seen_asins.add(asin)

                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, "h2 a span")
                    link_elem = item.find_element(By.CSS_SELECTOR, "h2 a")
                    price_whole = item.find_elements(By.CSS_SELECTOR, ".a-price-whole")
                    price_frac = item.find_elements(By.CSS_SELECTOR, ".a-price-fraction")

                    title = title_elem.text.strip()
                    link = link_elem.get_attribute("href")
                    price = ""
                    if price_whole:
                        price = f"${price_whole[0].text.strip()}"
                        if price_frac:
                            price += price_frac[0].text.strip()

                    all_results.append({
                        "asin": asin,
                        "title": title,
                        "url": link,
                        "price": price,
                        "source": "selenium"
                    })
                except Exception:
                    continue

            time.sleep(random.uniform(1.5, 2.5))
    finally:
        driver.quit()

    print(f"✅ Selenium found {len(all_results)} ASINs for '{q}'")
    return all_results

# ==============================================================
# ⚙️ MAIN HANDLER
# ==============================================================

def handler(request, response):
    """
    Unified endpoint for Lovable / Vercel.
    1. Try Google API
    2. If no results → fallback to Selenium scraping
    """
    try:
        if request.method == "GET":
            q = request.args.get("q")
            if not q:
                return response.status(400).json({"error": "Missing ?q parameter"})

            # Try Google first
            google_results = google_search(q, limit=20)
            if google_results:
                print(f"✅ Google found {len(google_results)} results for '{q}'")
                return response.status(200).json({
                    "mode": "google",
                    "query": q,
                    "count": len(google_results),
                    "results": google_results
                })

            # Fallback to Selenium
            print(f"⚠️ Google found nothing for '{q}', falling back to Selenium...")
            amazon_results = selenium_amazon_search(q, max_pages=5)
            return response.status(200).json({
                "mode": "selenium",
                "query": q,
                "count": len(amazon_results),
                "results": amazon_results
            })

        elif request.method == "POST":
            body = request.json or {}
            queries = body.get("queries", [])
            if not queries:
                return response.status(400).json({"error": "Missing 'queries' array"})

            all_results = []
            for q in queries:
                print(f"➡️ Searching '{q}'...")
                google_results = google_search(q, limit=20)
                if google_results:
                    for r in google_results:
                        r["query"] = q
                        all_results.append(r)
                else:
                    print(f"⚠️ Google found nothing for '{q}', switching to Selenium...")
                    amazon_results = selenium_amazon_search(q, max_pages=5)
                    for r in amazon_results:
                        r["query"] = q
                        all_results.append(r)
                tnap()

            return response.status(200).json({
                "mode": "hybrid",
                "count": len(all_results),
                "results": all_results
            })

        return response.status(405).json({"error": "Unsupported method"})

    except Exception as e:
        print("❌ Handler error:", e)
        return response.status(500).json({"error": str(e)})

