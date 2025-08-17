#!/usr/bin/env python3
"""Open the page and print request/response headers for any .m3u8 network responses.
"""
from playwright.sync_api import sync_playwright
import sys

url = sys.argv[1] if len(sys.argv) > 1 else "https://sportzonline.site/channels/pt/sporttv2.php"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    found = []

    def on_response(response):
        try:
            u = response.url
            if ".m3u8" in u.lower():
                req = response.request
                print('---')
                print('URL:', u)
                print('Response status:', response.status)
                print('Response headers:')
                for k, v in response.headers.items():
                    print(f'  {k}: {v}')
                print('\nRequest headers:')
                for k, v in req.headers.items():
                    print(f'  {k}: {v}')
                # cookies on context
                print('\nContext cookies:')
                for c in context.cookies():
                    print('  ', c)
                found.append(u)
        except Exception as e:
            print('error', e)

    page.on('response', on_response)
    page.goto(url, timeout=30000)
    page.wait_for_timeout(6000)
    browser.close()

    if not found:
        print('No m3u8 responses captured')
    else:
        print('\nCaptured', len(found), 'm3u8 responses')
