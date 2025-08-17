#!/usr/bin/env python3
"""Validate an entry in iptv.m3u8 by tvg-id or display name.

Usage: python check_m3u_entry.py --tvg SPORT.TV2
"""
import argparse
import sys
from pathlib import Path
import requests


def find_entry(file_path: Path, tvg_id: str):
    text = file_path.read_text(encoding='utf-8')
    lines = text.splitlines()
    target_idx = None
    for i, line in enumerate(lines):
        if f'tvg-id="{tvg_id}"' in line:
            target_idx = i
            break
    if target_idx is None:
        # try numeric fallback like 'Sport TV 4'
        import re as _re
        m = _re.search(r"(\d+)$", tvg_id)
        if m:
            num = m.group(1)
            for i, line in enumerate(lines):
                if _re.search(rf"Sport\s*TV\s*{num}", line, _re.I):
                    target_idx = i
                    break
    if target_idx is None:
        return None

    # look ahead for EXT-VLC-OPT lines and the URL
    ref = None
    ua = None
    url = None
    for j in range(target_idx+1, min(len(lines), target_idx+12)):
        l = lines[j].strip()
        if not l:
            continue
        if l.startswith('#EXTVLCOPT:http-referrer='):
            ref = l.split('=',1)[1]
            continue
        if l.startswith('#EXTVLCOPT:http-user-agent='):
            ua = l.split('=',1)[1]
            continue
        if l.startswith('#'):
            continue
        # first non-comment non-empty is URL
        url = l
        break

    return {
        'ref': ref,
        'ua': ua,
        'url': url,
    }


def validate(url, ref=None, ua=None):
    print('Found URL:')
    print(url)

    print('\nTrying HEAD request (no extra headers)')
    try:
        h = requests.head(url, timeout=15, allow_redirects=True)
        print('Status:', h.status_code)
        for k in ('content-type','server','cache-control','content-length'):
            if k in h.headers:
                print(k+':', h.headers[k])
    except Exception as e:
        print('HEAD error:', e)

    print('\nTrying GET request without extra headers')
    try:
        r = requests.get(url, timeout=15, stream=True)
        print('Status:', r.status_code)
        print('Content-Type:', r.headers.get('content-type'))
        print('Server:', r.headers.get('server'))
        data = r.raw.read(512)
        print('First bytes (hex):', data[:80].hex())
        r.close()
    except Exception as e:
        print('GET error:', e)

    headers = {}
    if ua:
        headers['User-Agent'] = ua
    if ref:
        headers['Referer'] = ref
        headers['Origin'] = ref

    if headers:
        print('\nTrying GET request WITH extracted headers')
        try:
            r = requests.get(url, headers=headers, timeout=15, stream=True)
            print('Status:', r.status_code)
            print('Content-Type:', r.headers.get('content-type'))
            print('Server:', r.headers.get('server'))
            data = r.raw.read(512)
            print('First bytes (hex):', data[:80].hex())
            r.close()
        except Exception as e:
            print('GET error with headers:', e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tvg', required=True, help='tvg-id or Sport TV name (e.g. SPORT.TV2)')
    parser.add_argument('--file', default='iptv.m3u8')
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print('File not found:', path)
        sys.exit(2)

    entry = find_entry(path, args.tvg)
    if not entry:
        print('Could not find entry for', args.tvg)
        sys.exit(3)
    if not entry['url']:
        print('No URL found for', args.tvg)
        sys.exit(4)

    validate(entry['url'], ref=entry['ref'], ua=entry['ua'])


if __name__ == '__main__':
    main()
