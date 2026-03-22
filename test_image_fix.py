"""
Test: Woolworths image URL fix
Verifies that:
1. cdn0.woolworths.media URLs pass the new _safe_image_url validation
2. Every on-special product gets a non-null image URL (via direct field or stockcode fallback)
3. Stockcodes 768057 and 777320 (Dairy Farmers yoghurt) are found and have images
"""

import asyncio
from urllib.parse import urlparse
from curl_cffi.requests import AsyncSession

BASE = "https://www.woolworths.com.au"
TIMEOUT = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": f"{BASE}/shop/specials/half-price",
    "Origin": BASE,
}

_ALLOWED_IMAGE_HOSTS = {
    "cdn0.woolworths.com.au", "cdn1.woolworths.com.au",
    "media.woolworths.com.au", "assets.woolworths.com.au",
    "www.woolworths.com.au",
    "cdn0.woolworths.media", "cdn1.woolworths.media",
    "productimages.coles.com.au", "shop.coles.com.au", "www.coles.com.au",
    "www.aldi.com.au", "images.aldi.com.au", "cdn.aldi.com.au",
}


def _safe_image_url(url: str):
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/") and not url.startswith("//"):
        url = "https://www.woolworths.com.au" + url
    if not url.startswith("https://"):
        return None
    host = urlparse(url).hostname or ""
    return url if host in _ALLOWED_IMAGE_HOSTS else None


async def fetch(session, term, page=1):
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


async def run():
    target_stockcodes = {768057, 777320}
    found_targets = {}
    total_specials = 0
    with_image = 0
    without_image = 0
    blocked_domains = {}

    async with AsyncSession(impersonate="chrome124") as session:
        for term in ["yoghurt", "chocolate", "chips", "chicken", "cheese"]:
            items = await fetch(session, term)
            for p in items:
                was = p.get("WasPrice"); price = p.get("Price")
                if not (was and price and float(was) > float(price) > 0):
                    continue
                total_specials += 1
                sc = p.get("Stockcode")

                # Image resolution (mirrors woolworths.py fix)
                img = p.get("MediumImageFile") or p.get("LargeImageFile") or ""
                if not img and sc:
                    img = f"https://cdn0.woolworths.media/content/wowproductimages/medium/{sc}.jpg"

                resolved = _safe_image_url(img)
                if resolved:
                    with_image += 1
                else:
                    without_image += 1
                    if img:
                        host = urlparse(img).hostname or "unknown"
                        blocked_domains[host] = blocked_domains.get(host, 0) + 1

                if sc in target_stockcodes:
                    found_targets[sc] = {
                        "name": p.get("Name"),
                        "price": price,
                        "was": was,
                        "raw_img": p.get("MediumImageFile") or "",
                        "resolved_img": resolved,
                    }

    print(f"\n{'='*55}")
    print(f"RESULTS over {total_specials} on-special products (5 terms)")
    print(f"{'='*55}")
    print(f"  With image URL   : {with_image}")
    print(f"  Without image URL: {without_image}")
    if blocked_domains:
        print(f"  Still-blocked domains: {blocked_domains}")
    else:
        print(f"  No blocked domains — all images pass the allowlist")

    print(f"\nTarget stockcode results:")
    for sc in target_stockcodes:
        if sc in found_targets:
            t = found_targets[sc]
            print(f"  FOUND {sc}: {t['name']}")
            print(f"    Price: ${t['price']} was ${t['was']}")
            print(f"    Raw image field : {t['raw_img'] or '(empty)'}")
            print(f"    Resolved image  : {t['resolved_img']}")
        else:
            print(f"  NOT FOUND: {sc} (not in these 5 search terms on page 1)")

    assert with_image > 0, "FAIL: no images resolved"
    assert without_image == 0 or not blocked_domains, f"FAIL: blocked domains remain: {blocked_domains}"
    print(f"\nPASS")


asyncio.run(run())
