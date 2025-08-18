#!/usr/bin/env python3
r"""Orchestrator: probe channels.json and update data/iptv.m3u8 when valid candidates found.

Usage:
  python .\scripts\update_playlist.py --dry-run --use-playwright
"""
from pathlib import Path
import json
import time
import random
import argparse
import os

BASE = Path(__file__).resolve().parent
CHANNELS_FILE = BASE / "channels.json"
IPTV_FILE = BASE.parent / "data" / "iptv.m3u8"
BACKUP_DIR = None 
CACHE_FILE = BASE / "last_good.json"

# reuse your helpers
from update_m3u8 import find_m3u8_in_page, _validate_url, update_m3u_file

# optional playwright capture
capture_fn = None
try:
    from update_m3u8_playwright import capture_m3u8_from_page as capture_fn
except Exception:
    capture_fn = None

def probe_one_source(src, timeout=12, use_playwright=False):
    """Return list of candidate tuples: (url, referer, ua, cookies, method)"""
    out = []
    try:
        m = find_m3u8_in_page(src, timeout=timeout)
        if m:
            out.append((m, None, None, None, "requests"))
            return out
    except Exception:
        pass

    if use_playwright and capture_fn:
        try:
            candidates = capture_fn(src, timeout=timeout)
            for c in candidates:
                if not c:
                    continue
                url = c[0]
                referer = c[1] if len(c) > 1 else None
                ua = c[2] if len(c) > 2 else None
                cookies = c[3] if len(c) > 3 else None
                out.append((url, referer, ua, cookies, "playwright"))
        except Exception:
            pass
    return out

def tvg_variants(key):
    v = [key]
    if not key.endswith('.pt'):
        v.append(key + '.pt')
    v.append(key.replace('.', ' '))
    return list(dict.fromkeys(v))

def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save_cache(c):
    try:
        CACHE_FILE.write_text(json.dumps(c, indent=2), encoding='utf-8')
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-playwright", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--pause", type=float, default=3.0, help="min pause between probes (seconds)")
    args = ap.parse_args()

    if not CHANNELS_FILE.exists() or not IPTV_FILE.exists():
        print("Missing channels.json or iptv.m3u8")
        return

    channels = json.loads(CHANNELS_FILE.read_text(encoding='utf-8'))
    cache = load_cache()

    # Configurable threshold (minutes). Can override with env var CHECK_THRESHOLD_MINUTES.
    THRESHOLD_MIN = int(os.environ.get("CHECK_THRESHOLD_MINUTES", "30"))
    THRESHOLD = THRESHOLD_MIN * 60

    # If no cache or cache empty -> proceed to probe so we populate it.
    if not cache:
        print("No cache found — proceeding to probe to populate last_good.json")
    else:
        # Find the nearest expiry we know about
        now = time.time()
        nearest = None
        for v in cache.values():
            exp = v.get("expires_at")
            if isinstance(exp, (int, float)):
                if nearest is None or exp < nearest:
                    nearest = exp
        # If we have an expiry and it's not within the threshold, exit early.
        if nearest and (nearest - now > THRESHOLD):
            mins = int((nearest - now) / 60)
            print(f"No tokens expiring within {THRESHOLD_MIN} minutes (nearest in ~{mins}m). Exiting.")
            return

    changed = False

    for channel_key, sources in channels.items():
        print(f"\n== {channel_key} ==")
        candidate = None

        # try cache first
        cinfo = cache.get(channel_key)
        if cinfo:
            url = cinfo.get("url")
            expires = cinfo.get("expires_at", 0)
            if url and time.time() < expires:
                ok = _validate_url(url, None, None, timeout=args.timeout)
                if ok:
                    print("Using cached url")
                    candidate = (url, None, None)

        if not candidate:
            for src in sources:
                print(" probing", src)
                candidates = probe_one_source(src, timeout=args.timeout, use_playwright=args.use_playwright)
                if not candidates:
                    print("  no candidates")
                for (url, ref, ua, cookies, method) in candidates:
                    if not url:
                        continue
                    print("  candidate:", url[:120], "...", method)
                    ok = _validate_url(url, ref, ua, cookies=cookies, timeout=args.timeout)
                    print("   valid?", ok)
                    if ok:
                        candidate = (url, ref, ua)
                        # set expiry from ?e=timestamp if present, else 10m
                        expires = time.time() + 60 * 10
                        import re
                        m = re.search(r"[?&]e=(\d{9,10})", url)
                        if m:
                            try:
                                expires = int(m.group(1)) - 30
                            except Exception:
                                pass
                        cache[channel_key] = {"url": url, "expires_at": expires}
                        break
                if candidate:
                    break
                time.sleep(args.pause + random.random()*2)

        if not candidate:
            print(" No valid candidate for", channel_key)
            continue

        new_url, ref, ua = candidate
        updated_ok = False
        for tvg in tvg_variants(channel_key):
            try:
                ok = update_m3u_file(IPTV_FILE, tvg, new_url, dry_run=args.dry_run, referrer=ref, user_agent=ua, backup_dir=BACKUP_DIR, group_filter="HD")
                # update_m3u_file should return truthy on success (existing helper)
                if ok:
                    print(" Updated", tvg)
                    changed = True
                    updated_ok = True
                    break
            except Exception as e:
                # continue checking other variants
                continue
        if not updated_ok:
            print(" Could not map", channel_key, "to iptv entry")

    save_cache(cache)
    print("\nDone. changes made:" , changed)

if __name__ == "__main__":
    main()