#!/usr/bin/env python3
"""Use Playwright to open the page, capture network responses containing .m3u8,
then update the iptv file for SPORT.TV2 using the existing function.

Run with:
  python update_m3u8_playwright.py --page <url> --file iptv.m3u8 --dry-run

Note: Playwright must be installed and browsers installed (playwright install).
"""
import argparse
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("Playwright not installed. Install with: pip install playwright && playwright install")
    sys.exit(2)

# reuse updater
try:
    from update_m3u8 import update_m3u_file
except Exception:
    update_m3u_file = None


def capture_m3u8_from_page(url, timeout=20):
    found = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def on_request(route):
            pass

        def on_response(response):
            try:
                u = response.url
                if ".m3u8" in u.lower():
                        # store request headers too
                        req = response.request
                        headers = req.headers
                        found.append((u, headers.get('referer'), headers.get('user-agent')))
                # also check content-type header
                ct = response.headers.get("content-type", "")
                if "application/vnd.apple.mpegurl" in ct.lower() or "vnd.apple.mpegurl" in ct.lower():
                        if (response.url, headers.get('referer'), headers.get('user-agent')) not in found:
                            found.append((response.url, headers.get('referer'), headers.get('user-agent')))
            except Exception:
                pass

        page.on("response", on_response)

        page.goto(url, timeout=timeout * 1000)
        # wait a bit to let XHRs fire
        page.wait_for_timeout(5000)

        # also try evaluating the DOM for obvious urls
        try:
            html = page.content()
            import re

            matches = re.findall(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*", html)
            for m in matches:
                    if not any(m == f[0] for f in found):
                        found.append((m, None, None))
        except Exception:
            pass

        browser.close()
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True)
    parser.add_argument("--file", default="iptv.m3u8")
    parser.add_argument("--tvg", default="SPORT.TV2")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(3)

    print(f"Opening page in headless browser: {args.page}")
    try:
        candidates = capture_m3u8_from_page(args.page)
    except Exception as e:
        print("Error running Playwright:", e)
        sys.exit(4)

    if not candidates:
        print("No .m3u8 requests captured from the page.")
        sys.exit(5)

    print("Captured m3u8 candidates:")
    for c in candidates:
        print(" -", c)

    new, ref, ua = candidates[0]

    # If dry-run, just print what we'd do and exit
    if args.dry_run:
        print("Dry-run: would update:")
        print(" URL:", new)
        print(" Referer:", ref)
        print(" User-Agent:", ua)
        sys.exit(0)

    if update_m3u_file is None:
        print("Updater function not available (couldn't import update_m3u8). Exiting.")
        sys.exit(6)

    changed, old = update_m3u_file(file_path, args.tvg, new, dry_run=args.dry_run, referrer=ref, user_agent=ua)
    if not changed:
        print("No change needed; file already had the URL.")
    else:
        print(f"Updated {args.tvg} -> {new}")
        if old:
            print("Replaced:", old)


if __name__ == "__main__":
    main()
