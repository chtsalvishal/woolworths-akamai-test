"""
Final endpoint probe before implementation.

Targets the two most promising leads from JS mining:
  1. /PiesCategoriesWithSpecials — app pre-fetches this for specials categories
  2. /apis/ui/v2 and /apis/ui/v3 — versioned browse endpoints
  3. All 13 category IDs against browse/category (including 12 unknowns)
  4. Coverage expansion — top 15 high-yield terms x pages 1+2
  5. Estimate total achievable half-price coverage
"""

import json
import time
from curl_cffi import requests

BASE = "https://www.woolworths.com.au"
CDN  = "https://cdn1.woolworths.media"
TIMEOUT = 20

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


def get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=HEADERS,
                         impersonate="chrome124", timeout=TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def post(url, body):
    try:
        r = requests.post(url, json=body,
                          headers={**HEADERS, "Content-Type": "application/json"},
                          impersonate="chrome124", timeout=TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def flatten(data):
    prods = data.get("Products") or data.get("Bundles") or []
    out = []
    for item in prods:
        inner = item.get("Products") or []
        if inner:
            out.extend(inner)
        elif item.get("Stockcode"):
            out.append(item)
    return out


def discount_pct(p):
    was = float(p.get("WasPrice") or 0)
    now = float(p.get("Price") or 0)
    if was > 0 and now > 0 and was > now:
        return round((was - now) / was * 100, 1)
    return 0.0


# ══════════════════════════════════════════════════════════════════
# TEST 1: PiesCategoriesWithSpecials endpoint
# ══════════════════════════════════════════════════════════════════

print("=" * 65)
print("TEST 1: /PiesCategoriesWithSpecials endpoint variants")
print("=" * 65)

PIES_URLS = [
    f"{BASE}/apis/ui/PiesCategoriesWithSpecials",
    f"{BASE}/apis/ui/pies/categories/specials",
    f"{BASE}/apis/ui/pies/CategoriesWithSpecials",
    f"{BASE}/apis/ui/Pies/CategoriesWithSpecials",
    f"{BASE}/apis/ui/pies-categories-with-specials",
    f"{BASE}/apis/pies/CategoriesWithSpecials",
    f"{CDN}/pies/CategoriesWithSpecials",
    f"{CDN}/wowssr/a10/browser/PiesCategoriesWithSpecials.json",
]

for url in PIES_URLS:
    status, text = get(url)
    has_data = len(text) > 200 and status == 200
    marker = "✓ HIT!" if has_data else f"  {status}"
    print(f"  {marker}  {url.replace(BASE,'').replace(CDN,'')}  ({status}, {len(text)}b)")
    if has_data:
        print(f"  Preview: {text[:300]}")
    time.sleep(0.2)


# ══════════════════════════════════════════════════════════════════
# TEST 2: v2 / v3 browse endpoints
# ══════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("TEST 2: Versioned browse endpoints /apis/ui/v2 and /apis/ui/v3")
print("=" * 65)

BROWSE_BODY = {
    "CategoryId": "1_D5A2236",
    "PageNumber": 1, "PageSize": 36,
    "SortType": "TraderRelevance",
    "Url": "/shop/specials/half-price",
    "IsSpecial": True,
}

V_ENDPOINTS = [
    ("GET",  f"{BASE}/apis/ui/v2",                          {"CategoryId": "1_D5A2236", "PageNumber": 1, "pageSize": 36}),
    ("GET",  f"{BASE}/apis/ui/v3",                          {"CategoryId": "1_D5A2236", "PageNumber": 1, "pageSize": 36}),
    ("POST", f"{BASE}/apis/ui/v2/browse/category",          BROWSE_BODY),
    ("POST", f"{BASE}/apis/ui/v3/browse/category",          BROWSE_BODY),
    ("GET",  f"{BASE}/apis/ui/v2/Search/products",          {"searchTerm": "specials", "pageNumber": 1, "pageSize": 36}),
    ("GET",  f"{BASE}/apis/ui/v3/Search/products",          {"searchTerm": "specials", "pageNumber": 1, "pageSize": 36}),
    ("POST", f"{BASE}/apis/ui/v2/browse/specials",          BROWSE_BODY),
    ("POST", f"{BASE}/apis/ui/v3/browse/specials",          BROWSE_BODY),
]

for method, url, body_or_params in V_ENDPOINTS:
    if method == "POST":
        status, text = post(url, body_or_params)
    else:
        status, text = get(url, params=body_or_params)
    has_products = status == 200 and "Price" in text and "Name" in text and len(text) > 500
    marker = "✓ HIT!" if has_products else f"  {status}"
    short = url.replace(BASE, "")
    print(f"  {marker}  {method} {short}  ({status}, {len(text)}b)")
    if has_products:
        print(f"  Preview: {text[:300]}")
    time.sleep(0.3)


# ══════════════════════════════════════════════════════════════════
# TEST 3: All 13 category IDs via browse/category POST
# ══════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("TEST 3: All 13 category IDs — what do the unknown ones contain?")
print("=" * 65)

CATEGORY_IDS = [
    "1_2432B58",
    "1_39FD49C",
    "1_5AF3A0A",
    "1_61D6FEB",
    "1_6E4F4E4",
    "1_717A94B",
    "1_894D0A8",
    "1_8E4DA6F",
    "1_ACA2FC2",
    "1_B63CF9E",
    "1_D5A2236",  # known: half-price
    "1_DEB537E",
    "1_DEF0CCD",
]

for cat_id in CATEGORY_IDS:
    status, text = post(
        f"{BASE}/apis/ui/browse/category",
        {
            "CategoryId": cat_id,
            "PageNumber": 1, "PageSize": 10,
            "SortType": "TraderRelevance",
            "IsSpecial": True,
        },
    )
    # Even if 403, peek at the response for hints
    label = "(known: half-price)" if cat_id == "1_D5A2236" else ""
    print(f"  {cat_id} {label}: HTTP {status}  ({len(text)}b)  {text[:100]}")
    time.sleep(0.3)


# ══════════════════════════════════════════════════════════════════
# TEST 4: Coverage expansion — top 15 terms x 2 pages
# ══════════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("TEST 4: Coverage expansion — 90 high-yield terms x pages 1+2")
print("=" * 65)

EXPANDED_TERMS = [
    # Snacks & confectionery (highest yield)
    "lollies", "chocolate", "biscuits", "chips", "crackers", "muesli bar",
    "popcorn", "pretzels", "jelly", "gummy", "licorice", "caramel",
    "tim tam", "shapes", "twisties",
    # Beverages
    "cola", "soft drink", "energy drink", "sports drink", "iced tea",
    "sparkling water", "cordial",
    # Cleaning & personal care (very high yield)
    "detergent", "deodorant", "shampoo", "conditioner", "body wash",
    "toothpaste", "face wash", "moisturiser", "sunscreen", "razors",
    "dishwasher tablets", "bleach", "spray cleaner",
    # Meat
    "bacon", "chicken", "steak", "sausages", "ham", "turkey", "fish",
    # Dairy & fridge
    "yoghurt", "cheese", "butter", "dip", "cream cheese",
    # Frozen
    "ice cream", "frozen pizza", "frozen chips", "frozen vegetables",
    # Pantry
    "tuna", "soup", "rice", "cereal", "coffee", "tea", "pasta sauce",
    "baked beans", "coconut milk",
    # Health & vitamins
    "vitamins", "protein bar", "supplements",
    # Baby & kids
    "nappy", "baby food", "formula",
    # Pet
    "dog food", "cat food",
    # Alcohol
    "beer", "wine", "cider", "premix",
]

all_half = {}
all_disc = {}

for term in EXPANDED_TERMS:
    for page in [1, 2]:
        try:
            r = requests.get(
                f"{BASE}/apis/ui/Search/products",
                params={
                    "searchTerm": term,
                    "pageNumber": page,
                    "pageSize": 36,
                    "sortType": "TraderRelevance",
                    "isFeatured": "false",
                },
                headers=HEADERS,
                impersonate="chrome124",
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                break
            data = r.json()
            flat = flatten(data)
            if not flat:
                break

            page_half = 0
            page_disc = 0
            for p in flat:
                sc = str(p.get("Stockcode") or "")
                pct = discount_pct(p)
                if pct > 0:
                    all_disc[sc] = p
                    page_disc += 1
                if p.get("IsHalfPrice") or (40 <= pct <= 60):
                    all_half[sc] = p
                    page_half += 1

            if page == 1:
                total = data.get("TotalRecordCount") or len(flat)
                print(f"  '{term:22}' p1: {len(flat):>3} results, {page_disc:>3} disc, {page_half:>3} half")

            time.sleep(0.15)
        except Exception as e:
            print(f"  '{term}' p{page}: Error {e}")
            break

print(f"\n{'─'*65}")
print(f"  FINAL COVERAGE REPORT")
print(f"{'─'*65}")
print(f"  Total API calls made:        ~{len(EXPANDED_TERMS) * 2}")
print(f"  Unique discounted products:  {len(all_disc)}")
print(f"  Unique half-price products:  {len(all_half)}")

if all_half:
    print(f"\n  IsHalfPrice breakdown:")
    flag_true  = sum(1 for p in all_half.values() if p.get("IsHalfPrice"))
    flag_false = sum(1 for p in all_half.values() if not p.get("IsHalfPrice"))
    print(f"    IsHalfPrice == True  (exact): {flag_true}")
    print(f"    IsHalfPrice == False (math):  {flag_false}  ← discount 40-60%, flag not set")

    print(f"\n  Top categories by half-price count (sample 5 products each):")
    cat_buckets = {}
    for p in all_half.values():
        cats = p.get("SapCategories") or {}
        cat = next(iter(cats.values()), "Unknown") if isinstance(cats, dict) else "Unknown"
        cat_buckets[cat] = cat_buckets.get(cat, 0) + 1
    for cat, count in sorted(cat_buckets.items(), key=lambda x: -x[1])[:10]:
        print(f"    {cat}: {count}")

if len(all_half) >= 200:
    print(f"\n  ✓ STRONG COVERAGE — {len(all_half)} half-price products")
    print(f"  Ready to implement as ScrapingBee replacement.")
elif len(all_half) >= 100:
    print(f"\n  ~ GOOD COVERAGE — {len(all_half)} half-price products")
    print(f"  Workable. Add more niche terms to push higher.")
else:
    print(f"\n  ✗ LOW COVERAGE — {len(all_half)} products only")

print("\n" + "=" * 65)
print("DONE")
print("=" * 65)
