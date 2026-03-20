"""
Woolworths Specials Harvest Test

Key questions:
  1. Of the 703 "half price" search results, how many are actually IsHalfPrice == True?
  2. Does the browse category endpoint work with HTTP/1.1 (the stream error may be H2-specific)?
  3. Does searching with a blank/wildcard term + filtering by IsHalfPrice work?
  4. Can we find the right search term that returns ONLY half-price items?
  5. What does the specials page HTML actually contain in its <script> tags?
"""

import json
import re
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


def search_page(term: str, page: int, size: int = 36) -> dict | None:
    r = requests.get(
        f"{BASE}/apis/ui/Search/products",
        params={
            "searchTerm": term,
            "pageNumber": page,
            "pageSize": size,
            "sortType": "TraderRelevance",
            "isFeatured": "false",
        },
        headers=HEADERS,
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return None
    return r.json()


def flatten_products(data: dict) -> list:
    prods = data.get("Products") or []
    flat = []
    for item in prods:
        inner = item.get("Products") or []
        flat.extend(inner) if inner else flat.append(item)
    return flat


# ── Test 1: Harvest ALL pages of "half price" and count real specials ─────────

print("=" * 60)
print("TEST 1: Harvest all 703 'half price' results — count IsHalfPrice == True")
print("=" * 60)

total_fetched = 0
total_half_price = 0
total_on_special = 0
total_has_saving = 0
page = 1
total_pages = 20  # 703 / 36 = 19.5

while page <= total_pages:
    data = search_page("half price", page)
    if not data:
        print(f"  Page {page}: failed, stopping")
        break
    flat = flatten_products(data)
    if not flat:
        break
    total_fetched += len(flat)
    for p in flat:
        if p.get("IsHalfPrice"):
            total_half_price += 1
        if p.get("IsOnSpecial"):
            total_on_special += 1
        if (p.get("SavingsAmount") or 0) > 0:
            total_has_saving += 1
    print(f"  Page {page}: {len(flat)} products — running totals: "
          f"IsHalfPrice={total_half_price}, IsOnSpecial={total_on_special}, HasSaving={total_has_saving}")
    page += 1

print(f"\n  TOTAL FETCHED: {total_fetched}")
print(f"  IsHalfPrice == True: {total_half_price}  ({total_half_price/total_fetched*100:.1f}%)")
print(f"  IsOnSpecial == True: {total_on_special}  ({total_on_special/total_fetched*100:.1f}%)")
print(f"  SavingsAmount > 0:   {total_has_saving}  ({total_has_saving/total_fetched*100:.1f}%)")


# ── Test 2: Browse category with HTTP/1.1 forced ──────────────────────────────

print("\n" + "=" * 60)
print("TEST 2: Browse category POST with HTTP/1.1")
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
        http_version=1,  # Force HTTP/1.1
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)")
    print(f"  Preview: {r.text[:300]}")
    if r.status_code == 200:
        try:
            data = r.json()
            bundles = data.get("Bundles") or []
            items = [p for b in bundles for p in (b.get("Products") or [])]
            print(f"  Products: {len(items)}")
        except Exception:
            pass
except Exception as e:
    print(f"  Error: {e}")


# ── Test 3: Empty search term ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("TEST 3: Empty search term")
print("=" * 60)

try:
    r = requests.get(
        f"{BASE}/apis/ui/Search/products",
        params={"searchTerm": "", "pageNumber": 1, "pageSize": 36, "sortType": "TraderRelevance"},
        headers=HEADERS,
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)")
    if r.status_code == 200:
        data = r.json()
        flat = flatten_products(data)
        total = data.get("TotalRecordCount", "?")
        print(f"  TotalRecordCount: {total}  Products: {len(flat)}")
        half = sum(1 for p in flat if p.get("IsHalfPrice"))
        spec = sum(1 for p in flat if p.get("IsOnSpecial"))
        print(f"  IsHalfPrice: {half}  IsOnSpecial: {spec}")
except Exception as e:
    print(f"  Error: {e}")


# ── Test 4: Search different specials terms ────────────────────────────────────

print("\n" + "=" * 60)
print("TEST 4: Try different search terms — looking for high IsHalfPrice ratio")
print("=" * 60)

for term in ["", "chicken", "milk", "bread", "half", "50%", "was"]:
    try:
        data = search_page(term, 1)
        if data:
            flat = flatten_products(data)
            total = data.get("TotalRecordCount", "?")
            half = sum(1 for p in flat if p.get("IsHalfPrice"))
            spec = sum(1 for p in flat if p.get("IsOnSpecial"))
            saving = sum(1 for p in flat if (p.get("SavingsAmount") or 0) > 0)
            print(f"  '{term}': total={total}, page1={len(flat)}, IsHalfPrice={half}, IsOnSpecial={spec}, Saving={saving}")
    except Exception as e:
        print(f"  '{term}': Error: {e}")


# ── Test 5: Inspect specials HTML script tags for API calls / data ─────────────

print("\n" + "=" * 60)
print("TEST 5: Inspect specials HTML — look for API URLs or data blobs in scripts")
print("=" * 60)

try:
    r = requests.get(
        f"{BASE}/shop/specials/half-price",
        headers={**HEADERS, "Accept": "text/html,*/*"},
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  HTTP {r.status_code}  ({len(r.text):,} bytes)")
    html = r.text

    # Find all inline script tags
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    print(f"  Inline script blocks: {len(scripts)}")

    for i, s in enumerate(scripts):
        s = s.strip()
        if not s:
            continue
        # Look for API URLs or large data blobs
        if "/apis/" in s or "CategoryId" in s or "Bundles" in s or "IsHalfPrice" in s:
            print(f"  Script {i} contains API reference ({len(s)} chars): {s[:200]}")
        elif len(s) > 5000:
            print(f"  Script {i} is large ({len(s):,} chars) — first 100: {s[:100]}")
        elif "window." in s:
            print(f"  Script {i} sets window var: {s[:200]}")

    # Check for data-* attributes with JSON
    data_attrs = re.findall(r'data-(?:initial|state|props|json|config)=["\']({.*?})["\']', html)
    if data_attrs:
        print(f"\n  Found {len(data_attrs)} data-* JSON attributes")
        for a in data_attrs[:2]:
            print(f"  {a[:200]}")

    # Look for JSON-like structures directly in HTML (outside scripts)
    if "IsHalfPrice" in html:
        idx = html.index("IsHalfPrice")
        print(f"\n  'IsHalfPrice' appears in HTML at position {idx}. Context:")
        print(f"  {html[max(0,idx-50):idx+100]}")

except Exception as e:
    print(f"  Error: {e}")


print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
