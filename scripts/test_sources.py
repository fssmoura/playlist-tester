#!/usr/bin/env python3
"""Probe all configured source pages and report found .m3u8 candidates.

Reads `scripts/channels.json`, for each channel tries to find an m3u8 using
the requests-based `find_m3u8_in_page` from `update_m3u8.py`. If nothing is
found and Playwright is available (and --use-playwright is passed) it will
try a headless capture using `update_m3u8_playwright.capture_m3u8_from_page`.

The script validates each discovered .m3u8 using the `_validate_url` helper
and writes a `scripts/report.json` with results.

Run (dry-run, won't modify iptv file):
  & ".\.venv\Scripts\python.exe" ".\scripts\test_sources.py"
Optionally use Playwright capture (may require browsers installed):
  & ".\.venv\Scripts\python.exe" ".\scripts\test_sources.py" --use-playwright
"""
import json
import argparse
from pathlib import Path
from typing import Optional
import time

BASE = Path(__file__).resolve().parent
CHANNELS_FILE = BASE / "channels.json"
REPORT_FILE = BASE / "report.json"

try:
    from update_m3u8 import find_m3u8_in_page, _validate_url
except Exception as e:
    print("Could not import helpers from update_m3u8.py:", e)
    raise

capture_with_playwright = False
capture_fn = None
try:
    from update_m3u8_playwright import capture_m3u8_from_page
    capture_with_playwright = True
    capture_fn = capture_m3u8_from_page
except Exception:
    # Playwright optional; we'll only try it if user asks and it's importable
    capture_with_playwright = False


def probe_source(page_url: str, use_playwright: bool, timeout: int = 10):
    """Return list of (candidate_url, ref, ua, method) tuples or empty list."""
    results = []
    try:
        m = find_m3u8_in_page(page_url, timeout=timeout)
        if m:
            results.append((m, None, None, "requests"))
            return results
    except Exception as e:
        results.append((None, None, None, f"requests-error: {e!s}"))

    # fallback to Playwright capture if requested and available
    if use_playwright and capture_fn:
        try:
            candidates = capture_fn(page_url, timeout=timeout)
            # capture_fn returns list of (url, referer, user-agent)
            for c in candidates:
                # support (url, referer, user-agent, cookies) or (url, referer, user-agent)
                if isinstance(c, (list, tuple)) and len(c) >= 1:
                    url = c[0]
                    ref = c[1] if len(c) > 1 else None
                    ua = c[2] if len(c) > 2 else None
                    cookies = c[3] if len(c) > 3 else None
                    results.append((url, ref, ua, cookies, "playwright"))
            return results
        except Exception as e:
            results.append((None, None, None, f"playwright-error: {e!s}"))

    return results


def validate_candidate(url: str, ref: Optional[str], ua: Optional[str], cookies: Optional[dict] = None, timeout: int = 10):
    try:
        # forward cookies to the underlying validator when available
        ok = _validate_url(url, ref, ua, cookies=cookies, timeout=timeout)
        return bool(ok), None
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels-file", default=str(CHANNELS_FILE))
    parser.add_argument("--use-playwright", action="store_true", help="If set, fall back to Playwright capture when requests don't find candidates (Playwright must be installed)")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()

    cfile = Path(args.channels_file)
    if not cfile.exists():
        print("Channels file not found:", cfile)
        raise SystemExit(2)

    channels = json.loads(cfile.read_text(encoding="utf-8"))
    report = {
        "generated_at": time.time(),
        "channels": {}
    }

    for channel, sources in channels.items():
        print(f"\n== Checking {channel} ({len(sources)} sources) ==")
        channel_report = []
        for src in sources:
            print(f"- probing {src} ...", end=" ")
            candidates = probe_source(src, use_playwright=args.use_playwright, timeout=args.timeout)
            if not candidates:
                print("no candidates")
                channel_report.append({"source": src, "candidates": []})
                continue
            entry_list = []
            for item in candidates:
                # item can be (url, ref, ua, method) or (url, ref, ua, cookies, method)
                if len(item) == 4:
                    url, ref, ua, method = item
                    cookies = None
                else:
                    url, ref, ua, cookies, method = item

                if not url:
                    entry_list.append({"source": src, "url": None, "method": method, "note": ref or ua})
                    print(f"[{method}] error")
                    continue
                print(f"[{method}] found {url}")
                # always pass cookies when available so validation can reuse auth state
                valid, err = validate_candidate(url, ref, ua, cookies=cookies, timeout=args.timeout)

                print(f"   -> valid={valid}")
                entry = {"source": src, "url": url, "method": method, "referer": ref, "user-agent": ua, "valid": valid, "error": err}
                if cookies:
                    entry["cookies"] = cookies
                entry_list.append(entry)
            channel_report.append({"source": src, "candidates": entry_list})
        report["channels"][channel] = channel_report

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to: {REPORT_FILE}")


if __name__ == "__main__":
    main()
