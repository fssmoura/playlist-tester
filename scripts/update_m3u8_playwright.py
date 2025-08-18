#!/usr/bin/env python3
"""Playwright capture helper for finding .m3u8 URLs on a page.

Listens to network requests/responses, checks inline HTML, and opens iframe
embeds (src/srcdoc/data-src) to capture cross-origin player activity. Returns
tuples (url, referer, user-agent, cookies_dict).
"""
import argparse
import sys
import re
from typing import List, Tuple, Optional

# keep a realistic desktop UA to improve capture of player traffic
# avoid 'HeadlessChrome' substring which some sites detect and block
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.5790.170 Safari/537.36"

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("Playwright not installed. Install with: pip install playwright && playwright install")
    sys.exit(2)


def capture_m3u8_from_page(url: str, timeout: int = 30, headless: bool = True, save_debug: bool = False) -> List[Tuple[str, Optional[str], Optional[str], Optional[dict]]]:
    found: List[Tuple[str, Optional[str], Optional[str], Optional[dict]]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # set a desktop-like user-agent on the context to avoid some bot/UA checks
        context = browser.new_context(user_agent=DEFAULT_UA)
        page = context.new_page()

        def add_entry(u, headers, cookies):
            if not u:
                return
            referer = headers.get('referer') if headers else None
            ua = headers.get('user-agent') if headers else None
            if not any(u == f[0] for f in found):
                found.append((u, referer, ua, cookies))

        def on_request(req):
            try:
                u = req.url
                if u and '.m3u8' in u.lower():
                    headers = getattr(req, 'headers', {}) or {}
                    cookies = {c['name']: c['value'] for c in context.cookies()}
                    add_entry(u, headers, cookies)
            except Exception:
                pass

        def on_response(resp):
            try:
                u = resp.url
                if u and '.m3u8' in u.lower():
                    req = resp.request
                    headers = getattr(req, 'headers', {}) or {}
                    cookies = {c['name']: c['value'] for c in context.cookies()}
                    add_entry(u, headers, cookies)
                ct = (resp.headers.get('content-type') or '').lower()
                if 'mpegurl' in ct or 'vnd.apple.mpegurl' in ct:
                    req = resp.request
                    headers = getattr(req, 'headers', {}) or {}
                    cookies = {c['name']: c['value'] for c in context.cookies()}
                    add_entry(resp.url, headers, cookies)
            except Exception:
                pass

        page.on('request', on_request)
        page.on('response', on_response)

        page.goto(url, timeout=timeout * 1000)
        # wait to allow players/iframes to initialize
        page.wait_for_timeout(12000)

        # scan inline HTML for obvious m3u8 links
        try:
            html = page.content()
            matches = re.findall(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*", html)
            for m in matches:
                add_entry(m, None, None)
        except Exception:
            pass

        # also inspect video/source elements and some in-page script text for m3u8 references
        try:
            found_urls = page.evaluate('''() => {
                const urls = [];
                // video and source elements
                document.querySelectorAll('video, source').forEach(el => {
                    try {
                        const src = el.src || el.getAttribute('src') || el.dataset && (el.dataset.src || el.dataset.url);
                        if (src) urls.push(src);
                    } catch(e) {}
                });
                // inline script text may contain m3u8 links or player config
                document.querySelectorAll('script').forEach(s => {
                    try { if (s.textContent && s.textContent.indexOf('.m3u8') !== -1) urls.push(s.textContent); } catch(e) {}
                });
                return urls;
            }''')
            if found_urls:
                for u in found_urls:
                    if isinstance(u, str) and '.m3u8' in u:
                        # if the script text contains an URL, extract via regex
                        ms = re.findall(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*", u)
                        for m in ms:
                            add_entry(m, None, None)
        except Exception:
            pass

        # try clicking player tabs/buttons
        for label in ("Player 1", "Player 2", "Player 3", "Player", "player", "Play"):
            try:
                els = page.query_selector_all(f'text="{label}"')
                for el in els:
                    try:
                        el.click(timeout=800)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass
            except Exception:
                pass

        page.wait_for_timeout(2000)

        # inspect iframe elements and open their src/srcdoc/data-src values
        try:
            iframes = page.query_selector_all('iframe')
            seen = set()
            for iframe in iframes:
                try:
                    for attr in ('src', 'srcdoc', 'data-src', 'data-iframe', 'data-url'):
                        try:
                            v = iframe.get_attribute(attr)
                            if not v or v in seen:
                                continue
                            seen.add(v)
                            np = context.new_page()
                            np.on('request', on_request)
                            np.on('response', on_response)
                            try:
                                if attr == 'srcdoc':
                                    np.set_content(v)
                                else:
                                    if v.startswith('http'):
                                        np.goto(v, timeout=8000)
                                np.wait_for_timeout(3000)
                            except Exception:
                                pass
                            for label in ("Player 1", "Player 2", "Player 3", "Play", "player"):
                                try:
                                    els2 = np.query_selector_all(f'text="{label}"')
                                    for el2 in els2:
                                        try:
                                            el2.click(timeout=500)
                                            np.wait_for_timeout(600)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            try:
                                np.close()
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        page.wait_for_timeout(1000)

        # if nothing found and debug requested, save a screenshot + html for inspection
        if not found and save_debug:
            try:
                import time as _time, os as _os
                ts = _time.strftime('%Y%m%dT%H%M%S')
                png = _os.path.join('.', f'playwright_debug_{ts}.png')
                htmlf = _os.path.join('.', f'playwright_debug_{ts}.html')
                try:
                    page.screenshot(path=png, full_page=True)
                except Exception:
                    pass
                try:
                    _html = page.content()
                    open(htmlf, 'w', encoding='utf-8').write(_html)
                except Exception:
                    pass
            except Exception:
                pass

        browser.close()
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page', required=True)
    parser.add_argument('--headful', action='store_true', help='Run browser non-headless for debugging')
    parser.add_argument('--save-debug', action='store_true', help='Save screenshot and HTML when no m3u8 captured')
    args = parser.parse_args()

    mode = 'headful' if args.headful else 'headless'
    print(f"Opening page in {mode} browser: {args.page}")
    try:
        candidates = capture_m3u8_from_page(args.page, headless=(not args.headful), save_debug=args.save_debug)
    except Exception as e:
        print('Error running Playwright:', e)
        sys.exit(4)

    if not candidates:
        print('No .m3u8 requests captured from the page.')
        sys.exit(5)

    print('Captured m3u8 candidates:')
    for c in candidates:
        print(' -', c)


if __name__ == '__main__':
    main()
