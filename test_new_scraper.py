"""
Test: optimised Woolworths scraper
- asyncio.Semaphore(16) instead of fixed batches of 8
- Adaptive paging: pages 2-3 only for terms that yielded specials on page 1
- Filter: WasPrice > Price (IsHalfPrice is deprecated)
"""

import asyncio
import time
from curl_cffi.requests import AsyncSession

BASE        = "https://www.woolworths.com.au"
CONCURRENCY = 16
TIMEOUT     = 20
PAGES_PER_TERM = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": f"{BASE}/shop/specials/half-price",
    "Origin": BASE,
}

SEARCH_TERMS = [
    "lollies", "chocolate", "biscuits", "chips", "crackers", "muesli bar",
    "popcorn", "shapes", "licorice", "caramel", "gummy", "twisties",
    "tim tam", "pretzels", "nuts", "trail mix", "rice cakes", "protein bar",
    "cola", "soft drink", "energy drink", "sports drink", "iced tea",
    "sparkling water", "cordial", "juice", "kombucha", "coconut water",
    "detergent", "bleach", "dishwasher tablets", "spray cleaner",
    "laundry", "fabric softener", "disinfectant", "toilet paper", "paper towel",
    "deodorant", "shampoo", "conditioner", "body wash", "toothpaste",
    "face wash", "moisturiser", "sunscreen", "razors", "tampons", "pads",
    "hand wash", "lip balm",
    "vitamins", "supplements", "fish oil", "probiotics",
    "bacon", "chicken", "steak", "sausages", "ham", "turkey", "fish",
    "salmon", "tuna", "prawns", "lamb", "pork", "mince", "salami",
    "deli", "kransky",
    "yoghurt", "cheese", "butter", "cream cheese", "dip", "cream", "feta",
    "milk", "custard", "sour cream",
    "bread", "rolls", "wraps", "crumpets", "muffins", "bagels",
    "cereal", "muesli", "oats", "granola",
    "ice cream", "frozen pizza", "frozen chips", "frozen vegetables",
    "frozen meals", "gelato",
    "soup", "rice", "coffee", "tea", "pasta sauce", "baked beans",
    "olive oil", "coconut milk", "stock", "mayo", "tomato",
    "peanut butter", "jam", "honey", "vegemite", "vinegar", "soy sauce",
    "canned fish", "canned tomato", "lentils", "chickpeas",
    "nappy", "baby food", "dog food", "cat food", "wipes",
    "beer", "wine", "cider", "premix", "spirits",
    "maggi", "heinz", "birds eye", "san remo", "cobs", "arnott",
    "uncle tobys", "sanitarium", "weet-bix",
]


async def fetch_page(session, sem, term, page):
    async with sem:
        try:
            r = await session.get(
                f"{BASE}/apis/ui/Search/products",
                params={"searchTerm": term, "pageNumber": page, "pageSize": 36,
                        "sortType": "TraderRelevance", "isFeatured": "false"},
                headers=HEADERS, timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return []
            data = r.json()
            outer = data.get("Products") or []
            flat = []
            for item in outer:
                inner = item.get("Products") or []
                if inner: flat.extend(inner)
                elif item.get("Stockcode"): flat.append(item)
            return flat
        except Exception:
            return []


def is_special(item):
    was = item.get("WasPrice"); price = item.get("Price")
    return bool(was and price and float(was) > 0 and float(price) > 0 and float(was) > float(price))


async def run():
    seen = set()
    products = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async with AsyncSession(impersonate="chrome124") as session:
        # Phase 1: all page-1s concurrently
        p1_start = time.time()
        page1_results = await asyncio.gather(
            *[fetch_page(session, sem, term, 1) for term in SEARCH_TERMS],
            return_exceptions=True,
        )
        print(f"Phase 1 done in {time.time()-p1_start:.1f}s ({len(SEARCH_TERMS)} calls)")

        productive = []
        for term, items in zip(SEARCH_TERMS, page1_results):
            if isinstance(items, Exception) or not items: continue
            had = False
            for item in items:
                if not is_special(item): continue
                had = True
                sc = item.get("Stockcode")
                if sc in seen: continue
                if sc: seen.add(sc)
                products.append(item)
            if had: productive.append(term)

        print(f"After p1: {len(products)} specials, {len(productive)}/{len(SEARCH_TERMS)} terms productive")

        # Phase 2: pages 2-3 for productive terms only
        deeper = [(t, p) for t in productive for p in range(2, PAGES_PER_TERM+1)]
        if deeper:
            p2_start = time.time()
            deeper_results = await asyncio.gather(
                *[fetch_page(session, sem, t, p) for t, p in deeper],
                return_exceptions=True,
            )
            print(f"Phase 2 done in {time.time()-p2_start:.1f}s ({len(deeper)} calls, skipped {(len(SEARCH_TERMS)-len(productive))*(PAGES_PER_TERM-1)} calls)")
            for items in deeper_results:
                if isinstance(items, Exception) or not items: continue
                for item in items:
                    if not is_special(item): continue
                    sc = item.get("Stockcode")
                    if sc in seen: continue
                    if sc: seen.add(sc)
                    products.append(item)

    total_calls = len(SEARCH_TERMS) + len(deeper)
    print(f"Total API calls: {total_calls} (vs {len(SEARCH_TERMS)*PAGES_PER_TERM} without adaptive paging)")
    return products


if __name__ == "__main__":
    start = time.time()
    products = asyncio.run(run())
    elapsed = time.time() - start

    print(f"\n{'='*50}")
    print(f"RESULT: {len(products)} unique specials in {elapsed:.1f}s")
    print(f"{'='*50}")

    if products:
        print("\nSample (first 5):")
        for p in products[:5]:
            was = p.get("WasPrice"); now = p.get("Price")
            pct = round((float(was)-float(now))/float(was)*100, 1) if was and now else 0
            print(f"  {p.get('Name','?')[:55]} - ${now} (was ${was}, {pct}% off)")

    assert len(products) >= 500, f"FAIL: only {len(products)} specials"
    print(f"\nPASS: {len(products)} specials found")
