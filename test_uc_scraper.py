"""
Feasibility test for ScrapperWoolies.py approach on GitHub Actions.

Uses undetected_chromedriver + seleniumwire to attempt the same
interception-based scrape that works on a residential IP.

Expected outcomes:
  PASS  — UC patches bypass Akamai on this host (GitHub Actions IP)
  FAIL  — Akamai blocks at IP level before any browser challenge runs
          (same result as patchright test, different root cause than UC)

Prints enough detail to distinguish IP block vs browser detection block.
"""

import json
import time
import zlib

import undetected_chromedriver as uc
from seleniumwire import webdriver

BASE_URL = "https://www.woolworths.com.au/shop/browse/specials/half-price"
WAIT_SECONDS = 15  # give Akamai sensor script time to run


def main():
    print("=" * 60)
    print("  UC + SeleniumWire Scraper Feasibility Test")
    print("=" * 60)

    # ── Launch browser ────────────────────────────────────────────
    print("\n── STEP 1: Launch undetected_chromedriver ──────────────────")
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--lang=en-AU")

    sw_options = {
        "suppress_connection_errors": True,
        "verify_ssl": False,
    }

    driver = webdriver.Chrome(
        options=options,
        seleniumwire_options=sw_options,
    )

    try:
        # ── Navigate to specials page ─────────────────────────────
        print(f"\n── STEP 2: Navigate to specials page ───────────────────────")
        print(f"  → {BASE_URL}")
        driver.get(BASE_URL)

        print(f"  → Waiting {WAIT_SECONDS}s for page + Akamai sensor to run...")
        time.sleep(WAIT_SECONDS)

        title = driver.title
        page_source_len = len(driver.page_source)
        print(f"  → Page title: {title!r}")
        print(f"  → Page source length: {page_source_len:,} bytes")

        # ── Check Akamai cookies ──────────────────────────────────
        print(f"\n── STEP 3: Check Akamai cookies ────────────────────────────")
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        has_abck = "_abck" in cookies
        has_bmsz = "bm_sz" in cookies
        aka_a2   = cookies.get("AKA_A2", "not present")

        print(f"  _abck:  {'✓ PRESENT — ' + cookies['_abck'][:40] if has_abck else '✗ MISSING'}")
        print(f"  bm_sz:  {'✓ PRESENT' if has_bmsz else '✗ MISSING'}")
        print(f"  AKA_A2: {aka_a2}")

        if "Access Denied" in title or aka_a2 == "A":
            print("\n  ✗ VERDICT: IP-level block — Akamai rejected this host before JS ran.")
            print("  undetected_chromedriver cannot help here; the IP is blocklisted.")
            return

        if not has_abck:
            print("\n  ✗ VERDICT: No _abck cookie — Akamai challenge not solved.")
            return

        print("\n  ✓ Akamai cookies obtained!")

        # ── Check intercepted network requests ────────────────────
        print(f"\n── STEP 4: Scan intercepted network requests ───────────────")
        browse_requests = [
            r for r in driver.requests
            if r.response and "apis/ui/browse/category" in r.url
        ]
        print(f"  browse/category requests intercepted: {len(browse_requests)}")

        products_found = 0
        for req in browse_requests:
            try:
                body = req.response.body
                # Try gzip decompression
                try:
                    decompressed = zlib.decompress(body, 16 + zlib.MAX_WBITS)
                except zlib.error:
                    decompressed = body  # might be uncompressed
                data = json.loads(decompressed.decode("utf-8"))
                bundles = data.get("Bundles") or []
                for bundle in bundles:
                    prods = bundle.get("Products") or []
                    for p in prods:
                        if p.get("IsHalfPrice"):
                            products_found += 1
            except Exception as e:
                print(f"  Parse error: {e}")

        print(f"  IsHalfPrice products captured: {products_found}")

        if products_found > 0:
            print("\n  ✓ FULL PASS — UC + SeleniumWire works on this host!")
            print("  The ScrapperWoolies.py approach is viable for automation.")
        elif browse_requests:
            print("\n  ~ PARTIAL — Got browse/category responses but no IsHalfPrice products.")
            print("  May be on a non-specials page or filter needs adjustment.")
        else:
            print("\n  ~ PARTIAL — Akamai cookies obtained but no browse/category request captured.")
            print("  Page may not have loaded product data yet.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
