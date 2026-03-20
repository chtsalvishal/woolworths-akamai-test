"""
Woolworths Mobile API Feasibility Test

Tries every known/plausible Woolworths API pattern without a browser or
Akamai cookies. If any endpoint returns real product JSON, we can replace
ScrapingBee entirely with a free curl_cffi solution.

Each test prints PASS / PARTIAL / FAIL with a sample of the response so
we know exactly what worked and what to build on.
"""

import json
from curl_cffi import requests

# ── User agents to try ────────────────────────────────────────────────────────

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
)
UA_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Mobile/15E148 Safari/604.1"
)
UA_WOOLWORTHS_APP = "Woolworths/9.0.0 (iPhone; iOS 17.4; Scale/3.00)"

BASE = "https://www.woolworths.com.au"
TIMEOUT = 20

# ── Helpers ───────────────────────────────────────────────────────────────────

def _preview(text: str, n: int = 300) -> str:
    t = text.strip()
    return (t[:n] + "...") if len(t) > n else t

def _looks_like_products(text: str) -> bool:
    """Heuristic: does the response look like it contains product data?"""
    keywords = ["Price", "price", "Name", "name", "Product", "product",
                "Stockcode", "stockcode", "Bundles", "bundles", "Results", "results"]
    hits = sum(1 for k in keywords if k in text)
    return hits >= 3

def _count_products(data: dict) -> int:
    """Try to count products in various response shapes."""
    # Browse API shape
    bundles = data.get("Bundles") or []
    if bundles:
        return sum(len(b.get("Products") or []) for b in bundles)
    # Search/specials shape
    results = data.get("Products") or data.get("results") or data.get("Items") or []
    if isinstance(results, list):
        return len(results)
    return 0

def run_test(name: str, fn) -> bool:
    print(f"\n{'─'*60}")
    print(f"TEST: {name}")
    print('─'*60)
    try:
        result = fn()
        return result
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False

# ── Individual tests ──────────────────────────────────────────────────────────

def test_browse_api_no_cookies():
    """The web browse API without any cookies — expect failure but useful baseline."""
    r = requests.post(
        f"{BASE}/apis/ui/browse/category",
        json={
            "CategoryId": "1_D5A2236",
            "PageNumber": 1, "PageSize": 10,
            "SortType": "TraderRelevance",
            "Url": "/shop/specials/half-price/poultry-meat-seafood",
            "IsSpecial": True,
        },
        headers={"Content-Type": "application/json", "User-Agent": UA_DESKTOP},
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  Status: {r.status_code}  Length: {len(r.text)}")
    print(f"  Preview: {_preview(r.text)}")
    if r.status_code == 200 and _looks_like_products(r.text):
        print("  ✓ PASS — products returned without cookies!")
        return True
    print("  ✗ FAIL (expected — baseline only)")
    return False


def test_specials_json_endpoint():
    """Try the /shop/specials page and look for embedded __NEXT_DATA__ or JSON."""
    r = requests.get(
        f"{BASE}/shop/specials/half-price",
        headers={"User-Agent": UA_DESKTOP, "Accept-Language": "en-AU"},
        impersonate="chrome124",
        timeout=TIMEOUT,
    )
    print(f"  Status: {r.status_code}  Length: {len(r.text)}")
    if "Access Denied" in r.text or r.status_code in (403, 429):
        print("  ✗ FAIL — IP blocked (Access Denied)")
        return False
    # Look for embedded JSON blobs
    for marker in ["__NEXT_DATA__", "window.__data__", "window.INITIAL_STATE",
                   "ng-init", "woolworthsApp", "specials"]:
        if marker in r.text:
            print(f"  ~ PARTIAL — found marker '{marker}' in HTML")
    if _looks_like_products(r.text):
        print("  ✓ PASS — product data found in HTML!")
        return True
    print("  ✗ FAIL — no product data in HTML")
    return False


def test_api_subdomain():
    """Try api.woolworths.com.au — possible mobile/app gateway."""
    for path in [
        "/v1/products/specials",
        "/v2/products/specials",
        "/apis/ui/browse/category",
        "/products",
    ]:
        url = f"https://api.woolworths.com.au{path}"
        try:
            r = requests.get(
                url,
                headers={"User-Agent": UA_WOOLWORTHS_APP},
                impersonate="chrome124",
                timeout=10,
            )
            print(f"  {url} → HTTP {r.status_code}  ({len(r.text)} bytes)")
            if r.status_code == 200 and _looks_like_products(r.text):
                print(f"  ✓ PASS — products at {url}!")
                print(f"  Preview: {_preview(r.text)}")
                return True
        except Exception as e:
            print(f"  {url} → Error: {e}")
    print("  ✗ FAIL — no usable api.woolworths.com.au endpoint found")
    return False


def test_mobile_gateway():
    """Try known mobile gateway subdomains."""
    subdomains = [
        "mobile-gateway.woolworths.com.au",
        "prod.mobile-gateway.woolworths.com.au",
        "app.woolworths.com.au",
        "mobileapi.woolworths.com.au",
    ]
    for sub in subdomains:
        try:
            r = requests.get(
                f"https://{sub}/",
                headers={"User-Agent": UA_WOOLWORTHS_APP},
                impersonate="chrome124",
                timeout=10,
            )
            print(f"  {sub} → HTTP {r.status_code}  ({len(r.text)} bytes)")
            if r.status_code not in (404, 000) and len(r.text) > 100:
                print(f"  ~ PARTIAL — {sub} is live! Preview: {_preview(r.text, 150)}")
        except Exception as e:
            print(f"  {sub} → {type(e).__name__}: {e}")
    return False  # informational only


def test_everyday_rewards_api():
    """Everyday Rewards (Woolworths loyalty) has a separate API — may expose products."""
    endpoints = [
        ("https://api.woolworthsrewards.com.au/wx/v1/rewards/specials", "GET"),
        ("https://api.woolworthsrewards.com.au/wx/v1/products/specials", "GET"),
        ("https://www.woolworthsrewards.com.au/wx/v1/specials", "GET"),
    ]
    for url, method in endpoints:
        try:
            r = requests.request(
                method, url,
                headers={"User-Agent": UA_MOBILE, "Accept": "application/json"},
                impersonate="chrome124",
                timeout=10,
            )
            print(f"  {url} → HTTP {r.status_code}")
            if r.status_code == 200:
                print(f"  Preview: {_preview(r.text)}")
                if _looks_like_products(r.text):
                    print("  ✓ PASS — products found via Everyday Rewards API!")
                    return True
        except Exception as e:
            print(f"  {url} → Error: {e}")
    print("  ✗ FAIL — no product data via Everyday Rewards API")
    return False


def test_search_api_no_cookies():
    """Woolworths search API — sometimes less protected than browse."""
    endpoints = [
        f"{BASE}/apis/ui/Search/products?searchTerm=specials&pageNumber=1&pageSize=20&sortType=TraderRelevance&isFeatured=false",
        f"{BASE}/apis/ui/products/specials?pageNumber=1&pageSize=20",
        f"{BASE}/apis/ui/specials?pageNumber=1&pageSize=20",
    ]
    for url in endpoints:
        try:
            r = requests.get(
                url,
                headers={
                    "User-Agent": UA_DESKTOP,
                    "Accept": "application/json",
                    "Referer": f"{BASE}/shop/specials",
                },
                impersonate="chrome124",
                timeout=TIMEOUT,
            )
            print(f"  {url[-60:]} → HTTP {r.status_code}  ({len(r.text)} bytes)")
            if r.status_code == 200 and _looks_like_products(r.text):
                try:
                    data = r.json()
                    count = _count_products(data)
                    print(f"  ✓ PASS — {count} products found!")
                    print(f"  Preview: {_preview(r.text)}")
                    return True
                except Exception:
                    print(f"  Preview: {_preview(r.text)}")
        except Exception as e:
            print(f"  Error: {e}")
    print("  ✗ FAIL")
    return False


def test_cdn_product_data():
    """Some retailers cache product JSON on CDN paths. Try common patterns."""
    paths = [
        "/content/dam/specials/specials.json",
        "/api/specials.json",
        "/static/specials.json",
        "/assets/specials.json",
    ]
    for path in paths:
        try:
            r = requests.get(
                f"{BASE}{path}",
                headers={"User-Agent": UA_DESKTOP},
                impersonate="chrome124",
                timeout=10,
            )
            print(f"  {path} → HTTP {r.status_code}")
            if r.status_code == 200 and _looks_like_products(r.text):
                print(f"  ✓ PASS! Preview: {_preview(r.text)}")
                return True
        except Exception as e:
            print(f"  {path} → Error: {e}")
    print("  ✗ FAIL")
    return False


def test_sitemap_and_rss():
    """Sitemaps and RSS feeds sometimes expose product/specials data."""
    urls = [
        f"{BASE}/sitemap.xml",
        f"{BASE}/feed/specials.rss",
        f"{BASE}/specials.rss",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": UA_DESKTOP},
                             impersonate="chrome124", timeout=10)
            print(f"  {url} → HTTP {r.status_code}  ({len(r.text)} bytes)")
            if r.status_code == 200 and len(r.text) > 500:
                print(f"  ~ Found content. Preview: {_preview(r.text, 200)}")
        except Exception as e:
            print(f"  {url} → Error: {e}")
    return False  # informational only


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Woolworths Mobile API Feasibility Test")
    print("  (no browser, no ScrapingBee, no proxies)")
    print("=" * 60)

    results = {
        "Browse API (no cookies) — baseline":   run_test("Browse API without cookies (baseline)", test_browse_api_no_cookies),
        "Specials HTML embedded JSON":           run_test("Specials page — embedded JSON", test_specials_json_endpoint),
        "api.woolworths.com.au subdomains":      run_test("api.woolworths.com.au subdomains", test_api_subdomain),
        "Mobile gateway subdomains":             run_test("Mobile gateway subdomains", test_mobile_gateway),
        "Everyday Rewards API":                  run_test("Everyday Rewards API", test_everyday_rewards_api),
        "Search/specials API (no cookies)":      run_test("Search & specials API without cookies", test_search_api_no_cookies),
        "CDN / static JSON paths":               run_test("CDN / static JSON paths", test_cdn_product_data),
        "Sitemap / RSS":                         run_test("Sitemap and RSS feeds", test_sitemap_and_rss),
    }

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    any_pass = False
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
        if passed:
            any_pass = True

    print()
    if any_pass:
        print("  ✓ At least one approach works — full implementation is viable!")
    else:
        print("  ✗ No approach worked on this host/IP.")
        print("  Woolworths data requires residential IP + browser for all endpoints.")


if __name__ == "__main__":
    main()
