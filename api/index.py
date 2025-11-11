import os
import re
import time
import random
import requests
from urllib.parse import urlparse, parse_qs

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")

def tnap():
    time.sleep(random.uniform(0.25, 0.6))

def extract_asin(url):
    pats = (r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})", r"/gp/aw/d/([A-Z0-9]{10})")
    for pat in pats:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def google_search(q, limit=20):
    base = "https://www.googleapis.com/customsearch/v1"
    results, start = [], 1
    while len(results) < limit:
        num = min(10, limit - len(results))
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CX,
            "q": q,
            "num": num,
            "start": start,
            "gl": "ca",
            "hl": "en",
            "fields": "items(link,title)"
        }
        try:
            r = requests.get(base, params=params, timeout=15)
            data = r.json()
            for it in data.get("items", []):
                link, title = it.get("link", ""), it.get("title", "")
                if "amazon.ca" in link:
                    results.append({
                        "asin": extract_asin(link),
                        "title": title,
                        "url": link
                    })
        except Exception as e:
            print("Error:", e)
            break
        start += num
        tnap()
    return results

def handler(request, response):
    try:
        if request.method == "GET":
            q = request.args.get("q")
            if not q:
                return response.status(400).json({"error": "Missing ?q"})
            res = google_search(q, 20)
            return response.status(200).json({"query": q, "results": res})

        elif request.method == "POST":
            body = request.json or {}
            queries = body.get("queries", [])
            if not queries:
                return response.status(400).json({"error": "Missing queries array"})
            allres = []
            for q in queries:
                for item in google_search(q, 20):
                    item["query"] = q
                    allres.append(item)
            return response.status(200).json({"count": len(allres), "results": allres})

        return response.status(405).json({"error": "Method not allowed"})
    except Exception as e:
        return response.status(500).json({"error": str(e)})
