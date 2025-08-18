#!/usr/bin/env python3
"""Playwright capture helper for finding .m3u8 URLs on a page."""
import argparse
import sys
import re
import json
import time
from typing import List, Tuple, Optional, Dict, Any

# Use exact Edge user agent that worked for you
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    print("Playwright not installed. Install with: pip install playwright && playwright install")
    sys.exit(2)

DEBUG = False

def log(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

def capture_m3u8_from_page(url: str, timeout: int = 30, headless: bool = True, save_debug: bool = False) -> List[Tuple[str, Optional[str], Optional[str], Optional[dict]]]:
    """Capture m3u8 URLs from a page using Playwright."""
    found: List[Tuple[str, Optional[str], Optional[str], Optional[dict]]] = []
    is_thedaddy = 'thedaddy.top' in url or 'thedaddy.to' in url
    
    # For thedaddy sites, always use visible browser
    if is_thedaddy:
        headless = False
        log("Forced visible browser for thedaddy site")
    
    with sync_playwright() as p:
        browser_type = p.chromium
        
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-web-security',  # Important for cross-origin requests
            '--disable-features=IsolateOrigins,site-per-process',
            f'--user-agent={DEFAULT_UA}'
        ]
        
        browser = browser_type.launch(
            headless=headless,
            args=browser_args
        )
        
        # Create context with stealth settings
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='Europe/London',
            permissions=['geolocation'],
            ignore_https_errors=True
        )
        
        # Add anti-detection script
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = context.new_page()
        
        # Setup m3u8 capture
        def add_entry(u, headers, cookies):
            if not u or '.m3u8' not in u.lower():
                return
            referer = headers.get('referer') if headers else None
            ua = headers.get('user-agent') if headers else None
            if not any(u == f[0] for f in found):
                log(f"Found m3u8: {u}")
                found.append((u, referer, ua, cookies))

        # Listen for m3u8 requests
        context.on('request', lambda req: 
            add_entry(req.url, req.headers, 
                   {c['name']: c['value'] for c in context.cookies()}) 
            if req.url and '.m3u8' in req.url.lower() else None)
        
        # Listen for m3u8 responses
        context.on('response', lambda resp: 
            add_entry(resp.url, resp.request.headers, 
                   {c['name']: c['value'] for c in context.cookies()})
            if ((resp.url and '.m3u8' in resp.url.lower()) or
               (resp.headers.get('content-type', '').lower().find('mpegurl') > -1)) else None)

        try:
            # Special handling for thedaddy
            if is_thedaddy:
                # Extract the stream ID from the URL
                stream_id = None
                if 'stream-' in url:
                    stream_id = url.split('stream-')[-1].split('.')[0]
                    log(f"Extracted stream ID: {stream_id}")
                
                # Step 1: Start with thedaddy embed URL
                embed_url = f"https://thedaddy.to/embed/stream-{stream_id}.php" if stream_id else url
                log(f"Navigating to embed URL: {embed_url}")
                page.goto(embed_url, timeout=timeout * 1000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)
                
                # Step 2: Look for jxoxkplay.xyz iframe
                iframe_url = None
                try:
                    iframe_info = page.evaluate("""() => {
                        const iframes = document.querySelectorAll('iframe');
                        for (const iframe of iframes) {
                            if (iframe.src && iframe.src.includes('jxoxkplay.xyz')) {
                                return iframe.src;
                            }
                        }
                        return null;
                    }""")
                    if iframe_url := iframe_info:
                        log(f"Found jxoxkplay iframe: {iframe_url}")
                except Exception as e:
                    log(f"Error finding iframe: {e}")
                
                # Step 3: Navigate to iframe if found
                if iframe_url:
                    log(f"Navigating to iframe URL: {iframe_url}")
                    page.goto(iframe_url, timeout=timeout * 1000, wait_until='domcontentloaded')
                    page.wait_for_timeout(5000)
                
                # Step 4: Direct approach - look for and navigate to veplay.top
                try:
                    # Either extract from page or construct using stream ID
                    veplay_url = None
                    
                    # Try to find veplay URL in page content
                    page_content = page.content()
                    veplay_matches = re.findall(r'(https?://veplay\.top/[^"\'\s<>]*)', page_content)
                    if veplay_matches:
                        veplay_url = veplay_matches[0]
                        log(f"Found veplay URL in content: {veplay_url}")
                    # If not found but we have stream ID, construct it
                    elif stream_id:
                        veplay_url = f"https://veplay.top/embed/e{stream_id}"
                        log(f"Constructed veplay URL: {veplay_url}")
                        
                    # Navigate to veplay if we have a URL
                    if veplay_url:
                        log(f"Navigating to veplay URL: {veplay_url}")
                        page.goto(veplay_url, timeout=timeout * 1000, wait_until='domcontentloaded')
                        page.wait_for_timeout(5000)
                        
                        # Try clicking on the player area to activate it
                        try:
                            page.mouse.click(640, 360)  # Click center of page
                            log("Clicked center of player")
                            page.wait_for_timeout(3000)
                        except Exception as e:
                            log(f"Error clicking player: {e}")
                except Exception as e:
                    log(f"Error processing veplay: {e}")
                
                # Step 5: As a last resort, direct construct the m3u8 URL using your format
                if not found and stream_id:
                    # Use similar pattern to what you found in browser
                    direct_urls = []
                    
                    # Add commonly used subdomains
                    for subdomain in ['5nhp186eg31fofnc', 'g644j2n1og4p9jbh', 'r90s83kafdp0jxzc']:
                        base_url = f"https://{subdomain}.chinese-restaurant-api.site/v3/variant/"
                        direct_urls.append(f"{base_url}VE1AO1NTbu8mbv12LxEWM21ycrNWYyR3LhVmZkJmM3MGZwIjMtUzYhJWL2QzN00SY2czNtQ2YlV2NkZjY/master.m3u8")
                    
                    # Try each constructed URL
                    for direct_url in direct_urls:
                        log(f"Trying direct m3u8 URL: {direct_url}")
                        try:
                            # Make request with correct referer
                            headers = {
                                'referer': 'https://veplay.top/',
                                'user-agent': DEFAULT_UA
                            }
                            cookies = {c['name']: c['value'] for c in context.cookies()}
                            add_entry(direct_url, headers, cookies)
                        except Exception as e:
                            log(f"Error with direct URL: {e}")
                
            else:
                # Standard handling for non-thedaddy sites
                log(f"Navigating to: {url}")
                page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')
                page.wait_for_load_state('networkidle', timeout=10000)
                page.wait_for_timeout(3000)
            
            # Save debug info if needed
            if save_debug and (DEBUG or not found):
                ts = time.strftime('%Y%m%dT%H%M%S')
                try:
                    screenshot_path = f'debug_screenshot_{ts}.png'
                    page.screenshot(path=screenshot_path)
                    log(f"Saved screenshot to {screenshot_path}")
                    
                    html_path = f'debug_html_{ts}.html'
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(page.content())
                    log(f"Saved HTML to {html_path}")
                except Exception as e:
                    log(f"Error saving debug info: {e}")
        
        except Exception as e:
            log(f"Error during page processing: {e}")
        finally:
            browser.close()
            
    return found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page', required=True)
    parser.add_argument('--headful', action='store_true', help='Run browser non-headless for debugging')
    parser.add_argument('--save-debug', action='store_true', help='Save screenshot and HTML when no m3u8 captured')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    args = parser.parse_args()
    
    global DEBUG
    DEBUG = args.debug

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
        url = c[0]
        referer = c[1] if len(c) > 1 else None
        ua = c[2] if len(c) > 2 else None
        cookies = c[3] if len(c) > 3 else None
        
        print(f" - URL: {url}")
        if referer:
            print(f"   Referer: {referer}")
        if ua:
            print(f"   User-Agent: {ua}")
        if cookies:
            print(f"   Cookies: {json.dumps(cookies, indent=2)}")
        print()

if __name__ == '__main__':
    main()
