"""
Akamai feasibility test — woolworths.com.au

Checks whether patchright (patched Playwright) running on this host can
obtain a valid Akamai _abck cookie from Woolworths, and whether curl_cffi
can then call the browse API with those cookies.

Prints a clear PASS / FAIL for each step so the result is obvious in logs.
"""

import asyncio
import json
import sys
from curl_cffi import requests as cf_requests
from patchright.async_api import async_playwright

BASE = "https://www.woolworths.com.au"

# One real category to test the API call
TEST_CATEGORY = {
    "cat_id": "1_D5A2236",
    "url_path": "/shop/specials/half-price/poultry-meat-seafood",
}


async def get_akamai_cookies() -> dict:
    print("\n── STEP 1: Launch patchright browser ──────────────────────────────")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-AU",
            timezone_id="Australia/Melbourne",
        )

        page = await ctx.new_page()

        print(f"  → Navigating to {BASE}/shop/specials/half-price ...")
        try:
            await page.goto(
                f"{BASE}/shop/specials/half-price",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except Exception as e:
            print(f"  ✗ Navigation failed: {e}")
            await browser.close()
            return {}

        print("  → Waiting 10s for Akamai sensor script to run ...")
        await asyncio.sleep(10)

        # Check page title to see if we got a real page or a block page
        title = await page.title()
        print(f"  → Page title: {title!r}")

        cookies = await ctx.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        await browser.close()

        # Report every cookie we got
        print(f"\n  Cookies received ({len(cookie_dict)}):")
        for name, value in cookie_dict.items():
            preview = value[:40] + "..." if len(value) > 40 else value
            print(f"    {name}: {preview}")

        return cookie_dict


def test_api_call(cookies: dict) -> bool:
    print("\n── STEP 2: Call Woolworths browse API via curl_cffi ────────────────")
    payload = {
        "CategoryId": TEST_CATEGORY["cat_id"],
        "PageNumber": 1,
        "PageSize": 36,
        "SortType": "TraderRelevance",
        "Url": TEST_CATEGORY["url_path"],
        "FormatObject": {},
        "IsSpecial": True,
    }
    try:
        r = cf_requests.post(
            f"{BASE}/apis/ui/browse/category",
            json=payload,
            cookies=cookies,
            impersonate="chrome124",
            headers={
                "Content-Type": "application/json",
                "Referer": f"{BASE}{TEST_CATEGORY['url_path']}",
                "Origin": BASE,
                "Accept": "application/json, text/plain, */*",
            },
            timeout=30,
        )
        print(f"  → HTTP {r.status_code}")
        print(f"  → Response length: {len(r.text)} bytes")
        print(f"  → First 200 chars: {r.text[:200]}")

        if r.status_code == 200:
            try:
                data = r.json()
                bundles = data.get("Bundles") or []
                items = [p for b in bundles for p in (b.get("Products") or [])]
                print(f"  → Products found: {len(items)}")
                return len(items) > 0
            except Exception:
                print("  ✗ Response is not valid JSON")
                return False
        return False

    except Exception as e:
        print(f"  ✗ API call failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("  Woolworths Akamai Feasibility Test")
    print("=" * 60)

    # ── Step 1: get cookies ──────────────────────────────────────
    cookies = await get_akamai_cookies()

    has_abck = "_abck" in cookies
    has_bmsz = "bm_sz" in cookies

    print("\n── STEP 1 RESULT ───────────────────────────────────────────")
    print(f"  _abck cookie:  {'✓ PRESENT' if has_abck else '✗ MISSING'}")
    print(f"  bm_sz cookie:  {'✓ PRESENT' if has_bmsz else '✗ MISSING'}")

    if not has_abck:
        print("\n  VERDICT: FAIL — Akamai challenge not solved.")
        print("  GitHub Actions IP may be blocked, or patchright needs tuning.")
        sys.exit(1)

    # ── Step 2: test API call ────────────────────────────────────
    api_ok = test_api_call(cookies)

    print("\n── STEP 2 RESULT ───────────────────────────────────────────")
    print(f"  API returned products: {'✓ YES' if api_ok else '✗ NO'}")

    print("\n── FINAL VERDICT ───────────────────────────────────────────")
    if has_abck and api_ok:
        print("  ✓ FULL PASS — patchright + curl_cffi works on this host.")
        print("  Safe to proceed with full implementation.")
        sys.exit(0)
    elif has_abck and not api_ok:
        print("  ~ PARTIAL PASS — Akamai cookie obtained but API call failed.")
        print("  May need to adjust headers or cookie forwarding.")
        sys.exit(2)
    else:
        print("  ✗ FAIL — Cannot obtain Akamai cookies on this host.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
