"""
Test: new Woolworths scraper (expanded 115-term search, 3 pages/term).
Validates that the scraper finds specials and the filter (WasPrice > Price) works.
"""

import asyncio
import time
from curl_cffi.requests import AsyncSession

BASE        = "https://www.woolworths.com.au"
CONCURRENCY = 8
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


async def fetch_page(session, term, page):
    try:
        r = await session.get(
            f"{BASE}/apis/ui/Search/products",
            params={
                "searchTerm": term,
                "pageNumber": page,
                "pageSize":   36,
                "sortType":   "TraderRelevance",
                "isFeatured": "false",
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        outer = data.get("Products") or []
        flat = []
        for item in outer:
            inner = item.get("Products") or []
            if inner:
                flat.extend(inner)
            elif item.get("Stockcode"):
                flat.append(item)
        return flat
    except Exception as e:
        return []


async def run():
    seen = set()
    products = []
    tasks = [(term, page) for term in SEARCH_TERMS for page in range(1, PAGES_PER_TERM + 1)]

    print(f"Total API calls planned: {len(tasks)}")

    async with AsyncSession(impersonate="chrome124") as session:
        for i in range(0, len(tasks), CONCURRENCY):
            batch = tasks[i:i + CONCURRENCY]
            results = await asyncio.gather(
                *[fetch_page(session, term, page) for term, page in batch],
                return_exceptions=True,
            )
            for items in results:
                if isinstance(items, Exception) or not items:
                    continue
                for item in items:
                    was   = item.get("WasPrice")
                    price = item.get("Price")
                    has_discount = (
                        was and price
                        and float(was) > 0
                        and float(price) > 0
                        and float(was) > float(price)
                    )
                    if not has_discount:
                        continue
                    sc = item.get("Stockcode")
                    if sc in seen:
                        continue
                    if sc:
                        seen.add(sc)
                    products.append(item)

            # Progress every 10 batches
            if (i // CONCURRENCY) % 10 == 0:
                print(f"  Batch {i//CONCURRENCY+1}/{len(tasks)//CONCURRENCY+1} done — {len(products)} specials so far")

    return products


if __name__ == "__main__":
    start = time.time()
    products = asyncio.run(run())
    elapsed = time.time() - start

    print(f"\n{'='*50}")
    print(f"RESULT: {len(products)} unique specials found in {elapsed:.1f}s")
    print(f"{'='*50}")

    if products:
        print("\nSample (first 10):")
        for p in products[:10]:
            was = p.get("WasPrice")
            now = p.get("Price")
            pct = round((float(was) - float(now)) / float(was) * 100, 1) if was and now else 0
            print(f"  {p.get('Name','?')[:55]}")
            print(f"    ${now} now  |  was ${was}  |  {pct}% off  |  IsHalfPrice={p.get('IsHalfPrice')}  |  IsOnSpecial={p.get('IsOnSpecial')}")

    assert len(products) >= 500, f"FAIL: only {len(products)} specials found, expected >= 500"
    print(f"\nPASS: {len(products)} specials found (>= 500 threshold)")
