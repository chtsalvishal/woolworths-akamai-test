"""
Woolworths Search API Deep Probe

The previous test confirmed /apis/ui/Search/products works without cookies.
This test investigates:
  1. Pagination — how many specials can we retrieve in total?
  2. IsSpecial filter — can we target only discounted items?
  3. Category filter — can we get half-price specials specifically?
  4. Page size limits — what is the max pageSize?
  5. Response shape — do we get WasPrice / SavingsAmount?
"""

import json
from curl_cffi import requests

BASE = "https://www.woolworths.com.au"
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": f"{BASE}/shop/specials/half-price",
}


def search(term: str, page: int = 1, size: int = 36, extra_params: dict = None) -> dict | None:
    params = {
        "searchTerm": term,
        "pageNumber": page,
        "pageSize": size,
        "sortType": "TraderRelevance",
        "isFeatured": "false",
    }
    if extra_params:
        params.update(extra_params)
    r = requests.get(
        f"{BASE}/apis/ui/Search/products",
        params=params,
        headers=HEADERS,
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)")
    if r.status_code != 200:
        print(f"  Body: {r.text[:200]}")
        return None
    return r.json()


def print_product_sample(products: list, n: int = 3):
    for p in products[:n]:
        name = p.get("Name", "?")
        price = p.get("Price", "?")
        was = p.get("WasPrice", None)
        saving = p.get("SavingsAmount", None)
        is_special = p.get("IsOnSpecial", p.get("IsSpecial", "?"))
        print(f"    • {name[:50]}")
        print(f"      Price: ${price}  Was: {was}  Saving: {saving}  Special: {is_special}")


# ── Test 1: pagination — how many half-price specials exist? ──────────────────

print("=" * 60)
print("TEST 1: Pagination — how many results exist for 'half price'?")
print("=" * 60)

data = search("half price specials", page=1, size=36)
if data:
    prods = data.get("Products") or []
    total_results = data.get("TotalRecordCount", data.get("SearchResultsCount", "?"))
    print(f"  TotalRecordCount: {total_results}")
    print(f"  Products on page 1: {len(prods)}")
    # Flatten nested Products
    flat = []
    for item in prods:
        inner = item.get("Products") or []
        flat.extend(inner)
    if not flat:
        flat = prods
    print(f"  Flat product count: {len(flat)}")
    print(f"  Sample:")
    print_product_sample(flat)
    print(f"\n  Full keys on first product:")
    if flat:
        print("  " + ", ".join(flat[0].keys()))


# ── Test 2: IsOnSpecial / specials-only search ────────────────────────────────

print("\n" + "=" * 60)
print("TEST 2: Search 'specials' with IsOnSpecial filter")
print("=" * 60)

data2 = search("specials", page=1, size=36, extra_params={"IsOnSpecial": "true"})
if data2:
    prods = data2.get("Products") or []
    flat = []
    for item in prods:
        inner = item.get("Products") or []
        flat.extend(inner)
    if not flat:
        flat = prods
    total = data2.get("TotalRecordCount", data2.get("SearchResultsCount", "?"))
    print(f"  TotalRecordCount: {total}")
    print(f"  Products: {len(flat)}")
    print(f"  Sample:")
    print_product_sample(flat)


# ── Test 3: page size limit ───────────────────────────────────────────────────

print("\n" + "=" * 60)
print("TEST 3: Max page size (try pageSize=100)")
print("=" * 60)

data3 = search("specials", page=1, size=100)
if data3:
    prods = data3.get("Products") or []
    flat = []
    for item in prods:
        inner = item.get("Products") or []
        flat.extend(inner)
    if not flat:
        flat = prods
    print(f"  Products returned with pageSize=100: {len(flat)}")


# ── Test 4: page 2 — does pagination work? ────────────────────────────────────

print("\n" + "=" * 60)
print("TEST 4: Page 2 of specials search")
print("=" * 60)

data4 = search("specials", page=2, size=36)
if data4:
    prods = data4.get("Products") or []
    flat = []
    for item in prods:
        inner = item.get("Products") or []
        flat.extend(inner)
    if not flat:
        flat = prods
    print(f"  Products on page 2: {len(flat)}")
    if flat:
        print(f"  First item on page 2: {flat[0].get('Name', '?')}")


# ── Test 5: browse category API (alternate endpoint for half-price) ───────────

print("\n" + "=" * 60)
print("TEST 5: Browse category POST — half-price specials category")
print("=" * 60)

try:
    r = requests.post(
        f"{BASE}/apis/ui/browse/category",
        json={
            "CategoryId": "1_D5A2236",
            "PageNumber": 1,
            "PageSize": 36,
            "SortType": "TraderRelevance",
            "Url": "/shop/specials/half-price",
            "IsSpecial": True,
        },
        headers={**HEADERS, "Content-Type": "application/json", "Origin": BASE},
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)  Preview: {r.text[:150]}")
except Exception as e:
    print(f"  Error: {e}")


# ── Test 6: Specials page embedded JSON — extract __NEXT_DATA__ ───────────────

print("\n" + "=" * 60)
print("TEST 6: Extract __NEXT_DATA__ from specials HTML page")
print("=" * 60)

try:
    r = requests.get(
        f"{BASE}/shop/specials/half-price",
        headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"},
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)")
    html = r.text
    marker = "__NEXT_DATA__"
    idx = html.find(marker)
    if idx == -1:
        print("  __NEXT_DATA__ NOT found in page")
    else:
        # Extract JSON blob between the <script> tags
        start = html.find("{", idx)
        # Find matching closing brace
        depth = 0
        end = start
        for i, ch in enumerate(html[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth == 0:
                end = i + 1
                break
        blob = html[start:end]
        print(f"  __NEXT_DATA__ found, JSON length: {len(blob):,} bytes")
        try:
            nd = json.loads(blob)
            # Try to find products in the Next.js page props
            props = nd.get("props", {})
            page_props = props.get("pageProps", {})
            print(f"  pageProps keys: {list(page_props.keys())[:10]}")
            # Look for product-like data
            for key in page_props:
                val = page_props[key]
                if isinstance(val, (list, dict)):
                    s = json.dumps(val)
                    if "Price" in s and "Name" in s:
                        print(f"  Found product-like data under pageProps.{key} ({len(s):,} bytes)")
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
            print(f"  First 300 chars of blob: {blob[:300]}")
except Exception as e:
    print(f"  Error: {e}")


print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
