#!/usr/bin/env python3
"""Check SPORT.TV2 m3u8 URL accessibility and headers.

Prints status, important headers, and the first few bytes of the response.
"""
import re
import sys
from pathlib import Path
import requests

file_path = Path("iptv.m3u8")
if not file_path.exists():
    print("iptv.m3u8 not found")
    sys.exit(2)

text = file_path.read_text(encoding='utf-8')
lines = text.splitlines()
url = None
for i, line in enumerate(lines):
    if 'tvg-id="SPORT.TV2"' in line or 'Sport TV 2' in line:
        # look ahead for next non-comment non-empty line
        for j in range(i+1, min(len(lines), i+8)):
            l = lines[j].strip()
            if not l or l.startswith('#'):
                continue
            url = l
            break
        break

if not url:
    print('Could not find SPORT.TV2 URL in iptv.m3u8')
    sys.exit(3)

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

common_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
    'Referer': 'https://sportzonline.site/channels/pt/sporttv2.php',
    'Origin': 'https://sportzonline.site',
}

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

print('\nTrying GET request WITH common headers (Referer/Origin/User-Agent)')
try:
    r = requests.get(url, headers=common_headers, timeout=15, stream=True)
    print('Status:', r.status_code)
    print('Content-Type:', r.headers.get('content-type'))
    print('Server:', r.headers.get('server'))
    data = r.raw.read(512)
    print('First bytes (hex):', data[:80].hex())
    r.close()
except Exception as e:
    print('GET error with headers:', e)

print('\nDone')
