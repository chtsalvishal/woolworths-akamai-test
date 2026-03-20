"""
Woolworths Deep Specials Investigation

Three-pronged attack to extract half-price specials without the browse/category endpoint:

  1. ENDPOINT BLITZ   — 25 untested API endpoint variants
  2. JS MINING        — Extract every /apis/ URL from the 636KB wowApp.desktop.js
  3. CATEGORY SWEEP   — 55 grocery terms → filter WasPrice > Price → calc discount %
                        IsHalfPrice can be derived: discountPct ≈ 50% means half-price
                        No IsHalfPrice flag needed at all.

Key insight: the search API DOES return WasPrice and Price for discounted items.
             We just need enough coverage via search terms to find them all.
"""

import json
import re
import time
from curl_cffi import requests

BASE = "https://www.woolworths.com.au"
TIMEOUT = 20

HEADERS_JSON = {
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

HEADERS_HTML = {**HEADERS_JSON, "Accept": "text/html,application/xhtml+xml,*/*"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_json(url, params=None, method="GET", body=None):
    try:
        if method == "POST":
            r = requests.post(url, json=body, headers={**HEADERS_JSON, "Content-Type": "application/json"},
                              impersonate="chrome124", timeout=TIMEOUT)
        else:
            r = requests.get(url, params=params, headers=HEADERS_JSON,
                             impersonate="chrome124", timeout=TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def flatten(data):
    """Flatten Woolworths nested Products structure."""
    prods = data.get("Products") or data.get("products") or []
    out = []
    for item in prods:
        inner = item.get("Products") or []
        if inner:
            out.extend(inner)
        elif item.get("Stockcode") or item.get("stockcode"):
            out.append(item)
    return out


def discount_pct(p):
    """Calculate discount percentage from WasPrice/Price fields."""
    was = float(p.get("WasPrice") or 0)
    now = float(p.get("Price") or 0)
    if was > 0 and now > 0 and was > now:
        return round((was - now) / was * 100, 1)
    return 0.0


def is_approx_half_price(pct):
    """True if discount is between 40% and 60% (accounts for pricing quirks)."""
    return 40.0 <= pct <= 60.0


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ENDPOINT BLITZ
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("SECTION 1: ENDPOINT BLITZ — untested API variants")
print("=" * 70)

BROWSE_BODY = {
    "CategoryId": "1_D5A2236",
    "PageNumber": 1, "PageSize": 36,
    "SortType": "TraderRelevance",
    "Url": "/shop/specials/half-price",
    "IsSpecial": True,
}

ENDPOINTS = [
    # ── Browse variants ──────────────────────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/browse/specials",            {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/browse/Specials",            {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/browse/category",            {"categoryId": "1_D5A2236", "pageNumber": 1, "pageSize": 36, "isSpecial": "true"}, None),
    ("POST", f"{BASE}/apis/ui/browse/specials",            None, {"PageNumber": 1, "PageSize": 36}),
    ("POST", f"{BASE}/apis/ui/browse/specials/half-price", None, {"PageNumber": 1, "PageSize": 36}),
    ("POST", f"{BASE}/apis/ui/browse/Specials",            None, BROWSE_BODY),
    # ── Specials-specific endpoints ──────────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/Specials",                   {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/specials",                   {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/specials/half-price",        {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/specials/browse",            {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/products/specials",          {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/Products/specials",          {"pageNumber": 1, "pageSize": 36}, None),
    ("GET",  f"{BASE}/apis/ui/product-catalogue/specials", {"pageNumber": 1}, None),
    # ── Search variants ──────────────────────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/Search/products",            {"searchTerm": "specials", "pageNumber": 1, "pageSize": 36, "sortType": "HighestDiscount"}, None),
    ("GET",  f"{BASE}/apis/ui/Search/products",            {"searchTerm": "specials", "pageNumber": 1, "pageSize": 36, "sortType": "PriceLowestToHighest"}, None),
    ("GET",  f"{BASE}/apis/ui/Search/products",            {"searchTerm": "specials", "pageNumber": 1, "pageSize": 36, "IsOnSpecial": "true", "SpecialType": "HalfPrice"}, None),
    ("GET",  f"{BASE}/apis/ui/Search/products",            {"searchTerm": "", "pageNumber": 1, "pageSize": 36, "IsOnSpecial": "true"}, None),
    ("GET",  f"{BASE}/apis/ui/Search/specials",            {"pageNumber": 1, "pageSize": 36}, None),
    # ── Recommendations / personalised ───────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/Recommendations/specials",   {"pageNumber": 1}, None),
    # ── Content / CMS endpoints ──────────────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/content/specials",           None, None),
    ("GET",  f"{BASE}/apis/ui/Content/browse/specials",    None, None),
    # ── Catalogue / promotions ───────────────────────────────────────────────
    ("GET",  f"{BASE}/apis/ui/catalogue/specials",         {"pageNumber": 1}, None),
    ("GET",  f"{BASE}/apis/ui/promotions/half-price",      {"pageNumber": 1}, None),
    ("GET",  f"{BASE}/apis/ui/Promotions",                 {"type": "HalfPrice", "pageNumber": 1}, None),
    # ── Mobile / v2 ──────────────────────────────────────────────────────────
    ("GET",  f"{BASE}/apis/2.0/ui/browse/category",        {"categoryId": "1_D5A2236", "pageNumber": 1}, None),
]

wins = []
for method, url, params, body in ENDPOINTS:
    status, text = get_json(url, params=params, method=method, body=body)
    short = url.replace(BASE, "")
    has_products = ("Price" in text and "Name" in text and len(text) > 500)
    marker = "✓ HIT!" if (status == 200 and has_products) else ("~ 200" if status == 200 else f"  {status}")
    print(f"  {marker}  {method:4} {short[:60]} ({status}, {len(text):,}b)")
    if status == 200 and has_products:
        wins.append((method, url, params, body, text))
    time.sleep(0.3)

if wins:
    print(f"\n  ★ {len(wins)} endpoint(s) returned product data!")
    for method, url, params, body, text in wins:
        print(f"\n  ── {method} {url} ──")
        try:
            d = json.loads(text)
            flat = flatten(d)
            print(f"  Products: {len(flat)}")
            discounted = [p for p in flat if discount_pct(p) > 0]
            half_price = [p for p in discounted if is_approx_half_price(discount_pct(p))]
            print(f"  Discounted (WasPrice > Price): {len(discounted)}")
            print(f"  ~Half price (40-60% off):      {len(half_price)}")
            for p in half_price[:3]:
                pct = discount_pct(p)
                print(f"    • {p.get('Name','?')[:50]} — ${p.get('Price')} was ${p.get('WasPrice')} ({pct}% off)")
        except Exception as e:
            print(f"  Parse error: {e} — Preview: {text[:200]}")
else:
    print("\n  No new endpoints found in blitz.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — wowApp.js MINING
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("SECTION 2: wowApp.js MINING — extract /apis/ URLs from page JS")
print("=" * 70)

try:
    r = requests.get(f"{BASE}/shop/specials/half-price",
                     headers=HEADERS_HTML, impersonate="chrome124", timeout=30)
    html = r.text
    print(f"  HTML fetched: {len(html):,} bytes, HTTP {r.status_code}")

    # Extract all <script src="..."> external script URLs
    ext_scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
    print(f"  External script tags: {len(ext_scripts)}")
    for s in ext_scripts:
        print(f"    {s[:100]}")

    # Also search all inline + external scripts for /apis/ patterns
    # Inline scripts (already in HTML)
    all_script_content = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL))

    # Find all /apis/ui/... patterns
    api_patterns = re.findall(r'["\`](/apis/ui/[A-Za-z0-9/_\-\.]+)["\`]', all_script_content)
    unique_apis = sorted(set(api_patterns))
    print(f"\n  Unique /apis/ui/ paths found in inline scripts: {len(unique_apis)}")
    for p in unique_apis:
        print(f"    {p}")

    # Also look for category IDs
    cat_ids = re.findall(r'["\'](\d+_[A-Z0-9]{6,})["\']', all_script_content)
    unique_cats = sorted(set(cat_ids))
    print(f"\n  Category ID patterns found: {len(unique_cats)}")
    for c in unique_cats[:20]:
        print(f"    {c}")

    # Look for any fetch/http calls with specials paths
    specials_refs = re.findall(r'["\`][^"\'`]*specials[^"\'`]*["\`]', all_script_content, re.IGNORECASE)
    unique_refs = sorted(set(specials_refs))
    print(f"\n  'specials' path references in scripts: {len(unique_refs)}")
    for s in unique_refs[:20]:
        print(f"    {s[:120]}")

    # Fetch largest external script and mine it too
    wow_scripts = [s for s in ext_scripts if "wowApp" in s or "main" in s or "vendor" in s]
    if wow_scripts:
        for script_url in wow_scripts[:2]:
            full_url = script_url if script_url.startswith("http") else BASE + script_url
            print(f"\n  Fetching external script: {full_url[:100]}")
            try:
                rs = requests.get(full_url, headers=HEADERS_JSON, impersonate="chrome124", timeout=30)
                print(f"  → {rs.status_code}, {len(rs.text):,} bytes")
                ext_apis = re.findall(r'["\`](/apis/ui/[A-Za-z0-9/_\-\.]+)["\`]', rs.text)
                ext_unique = sorted(set(ext_apis))
                print(f"  → /apis/ui/ paths: {len(ext_unique)}")
                for p in ext_unique:
                    print(f"      {p}")
                ext_specials = re.findall(r'["\`][^"\'`]*specials[^"\'`]*["\`]', rs.text, re.IGNORECASE)
                for s in sorted(set(ext_specials))[:20]:
                    print(f"      specials ref: {s[:120]}")
            except Exception as e:
                print(f"  → Error: {e}")

except Exception as e:
    print(f"  Error fetching HTML: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — CATEGORY SWEEP (55 grocery terms → WasPrice math)
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("SECTION 3: CATEGORY SWEEP — 55 terms, WasPrice > Price filter")
print("=" * 70)
print("  Logic: discountPct = (WasPrice - Price) / WasPrice × 100")
print("  Half-price = 40–60% off (covers rounding in Woolworths pricing)")
print()

TERMS = [
    # Meat & Poultry
    "chicken", "beef", "pork", "lamb", "mince", "bacon", "steak",
    "sausages", "ham", "salami", "turkey", "veal", "chorizo",
    # Seafood
    "salmon", "tuna", "prawns", "fish", "seafood", "basa",
    # Dairy & Eggs
    "milk", "cheese", "yoghurt", "butter", "cream", "eggs", "feta",
    # Bread & Bakery
    "bread", "rolls", "wraps", "crumpets",
    # Breakfast & Cereal
    "cereal", "muesli", "oats", "weetbix",
    # Snacks & Confectionery
    "chips", "chocolate", "biscuits", "crackers", "lollies", "nuts",
    # Beverages
    "juice", "cola", "beer", "wine", "coffee",
    # Frozen
    "ice cream", "frozen pizza", "frozen meals",
    # Pantry
    "pasta", "rice", "soup", "olive oil",
    # Cleaning & Personal care
    "shampoo", "detergent", "toothpaste", "deodorant",
]

all_specials = {}      # stockcode → product dict
all_half_price = {}    # stockcode → product dict
term_results = []

for term in TERMS:
    try:
        r = requests.get(
            f"{BASE}/apis/ui/Search/products",
            params={
                "searchTerm": term,
                "pageNumber": 1,
                "pageSize": 36,
                "sortType": "TraderRelevance",
                "isFeatured": "false",
            },
            headers=HEADERS_JSON,
            impersonate="chrome124",
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            print(f"  '{term}': HTTP {r.status_code} — skip")
            time.sleep(0.5)
            continue

        data = r.json()
        flat = flatten(data)
        total = data.get("TotalRecordCount") or len(flat)

        specials_this = []
        half_this = []
        for p in flat:
            pct = discount_pct(p)
            sc = str(p.get("Stockcode") or p.get("stockcode") or "")
            if pct > 0:
                specials_this.append(p)
                all_specials[sc] = p
            if is_approx_half_price(pct):
                half_this.append(p)
                all_half_price[sc] = p

        term_results.append((term, total, len(flat), len(specials_this), len(half_this)))
        print(f"  '{term:20}': total={str(total):>6}, page1={len(flat):>3}, "
              f"discounted={len(specials_this):>3}, ~half-price={len(half_this):>3}")
        time.sleep(0.2)

    except Exception as e:
        print(f"  '{term}': Error: {e}")
        time.sleep(0.5)

# ── Summary ───────────────────────────────────────────────────────────────────

print(f"\n{'─'*70}")
print(f"  SWEEP SUMMARY")
print(f"{'─'*70}")
print(f"  Terms searched:              {len(TERMS)}")
print(f"  Unique discounted products:  {len(all_specials)}  (WasPrice > Price)")
print(f"  Unique ~half-price products: {len(all_half_price)}  (40-60% off)")

if all_half_price:
    print(f"\n  Sample half-price finds:")
    for p in list(all_half_price.values())[:10]:
        pct = discount_pct(p)
        print(f"    • {p.get('Name','?')[:55]}")
        print(f"      ${p.get('Price')} now  |  was ${p.get('WasPrice')}  |  {pct}% off  |  IsHalfPrice flag={p.get('IsHalfPrice')}")

if all_specials:
    print(f"\n  Discount distribution of all {len(all_specials)} discounted products:")
    buckets = {"<10%": 0, "10-25%": 0, "25-40%": 0, "40-60% (≈half)": 0, "60%+": 0}
    for p in all_specials.values():
        pct = discount_pct(p)
        if pct < 10:
            buckets["<10%"] += 1
        elif pct < 25:
            buckets["10-25%"] += 1
        elif pct < 40:
            buckets["25-40%"] += 1
        elif pct <= 60:
            buckets["40-60% (≈half)"] += 1
        else:
            buckets["60%+"] += 1
    for bucket, count in buckets.items():
        bar = "█" * count
        print(f"    {bucket:20}: {count:3}  {bar}")

# ── How many pages would cover all half-price items? ─────────────────────────

print(f"\n{'─'*70}")
print("  FEASIBILITY ASSESSMENT")
print(f"{'─'*70}")
top_terms = sorted(term_results, key=lambda x: x[4], reverse=True)[:10]
print(f"  Top 10 terms by half-price yield:")
for term, total, page1, disc, half in top_terms:
    print(f"    '{term:20}': {half:>3} half-price on page 1 of ~{(total//36)+1} pages")

total_hp_found = len(all_half_price)
print(f"\n  With 55 single-page searches ({55} API calls):")
print(f"    → {total_hp_found} unique half-price products found")
print(f"    → Adding page 2 for top terms could roughly double coverage")

if total_hp_found >= 50:
    print(f"\n  ✓ VIABLE — category sweep finds enough specials to be useful")
    print(f"    Full implementation: ~100 calls/run, 100% free, no proxy needed")
elif total_hp_found >= 20:
    print(f"\n  ~ PARTIAL — some specials found but coverage may be incomplete")
    print(f"    Supplementing with page 2 for top categories recommended")
else:
    print(f"\n  ✗ LOW YIELD — category sweep finds too few specials")
    print(f"    Residential proxy / ScraperAPI still needed for full coverage")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
