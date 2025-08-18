#!/usr/bin/env python3
"""Simple m3u8 updater for one channel (SPORT.TV2).

Usage:
  python update_m3u8.py --page <page_url> --file <iptv_file> [--tvg <TV_GID>] [--dry-run]

This finds the first .m3u8 URL on the page and replaces the URL following
the EXTINF line that contains the specified tvg-id (default: SPORT.TV2).
"""
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import requests
except ImportError:
    print("Missing dependency 'requests'. Install from requirements.txt or run: pip install requests")
    sys.exit(2)


M3U8_REGEX = re.compile(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*")


def find_m3u8_in_page(url, timeout=10):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    text = r.text
    # naive search for m3u8 urls
    matches = re.findall(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*", text)
    if not matches:
        return None
    # prefer ones that include sport or 8443 if present
    for m in matches:
        low = m.lower()
        if "sport" in low or ":8443" in low:
            return m
    return matches[0]


def _validate_url(url: str, referrer: Optional[str], user_agent: Optional[str], cookies: Optional[dict] = None, timeout: int = 10) -> bool:
    """Validate the candidate URL by issuing a GET with optional headers/cookies.

    Accept responses that either have an m3u8 content-type or whose body
    begins with M3U metadata ("#EXTM3U" / "#EXTINF"). This is more robust
    for CDNs that return application/octet-stream or obfuscated content-type.
    """
    headers = {}
    if referrer:
        headers["Referer"] = referrer
        headers["Origin"] = referrer
    if user_agent:
        headers["User-Agent"] = user_agent
    try:
        r = requests.get(url, headers=headers or None, cookies=cookies or None, timeout=timeout, stream=True)
        content_type = r.headers.get("content-type", "")
        status_ok = r.status_code == 200
        # read a small prefix of the body
        try:
            data = r.raw.read(2048)
        except Exception:
            data = b""
        r.close()

        # check common indicators
        data_text = ""
        try:
            data_text = data.decode('utf-8', errors='ignore')
        except Exception:
            data_text = ''

        if status_ok and ("mpegurl" in content_type.lower() or url.lower().endswith('.m3u8')):
            # likely an m3u8 even if content-type is non-standard
            return True
        if status_ok and ("#EXTM3U" in data_text or "#EXTINF" in data_text or data_text.strip().startswith('#EXT')):
            return True
        return False
    except Exception:
        return False


def update_m3u_file(file_path: Path, tvg_id: str, new_url: str, dry_run: bool = False, referrer: Optional[str] = None, user_agent: Optional[str] = None, backup_dir: Optional[Path] = None, group_filter: Optional[str] = None):
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # find the EXTINF line for the given tvg id
    target_idx = None
    for i, line in enumerate(lines):
        if f'tvg-id="{tvg_id}"' in line:
            if group_filter:
                import re as _re
                m = _re.search(r'group-title\s*=\s*"([^"]*)"', line, _re.I)
                # require an explicit group-title and exact match (case-insensitive)
                if not m:
                    continue
                group_value = m.group(1).strip()
                if group_value.lower() != group_filter.lower():
                    continue
            target_idx = i
            break

    # fallback: if the tvg-id isn't present, try a numeric fallback only when the
    # requested id is actually a SPORT.TV* id (e.g. SPORT.TV4). This avoids
    # accidental matches when the tvg-id is something like ELEVEN1 which would
    # otherwise match 'Sport TV 1'.
    if target_idx is None:
        tvg_upper = tvg_id.upper()
        if tvg_upper.startswith('SPORT.TV') or tvg_upper.startswith('SPORTTV'):
            import re as _re
            m = _re.search(r"(\d+)$", tvg_id)
            if m:
                num = m.group(1)
                for i, line in enumerate(lines):
                    if _re.search(rf"Sport\s*TV\s*{num}", line, _re.I):
                        target_idx = i
                        break

    if target_idx is None:
        raise RuntimeError(f"Could not find EXTINF entry for {tvg_id} in {file_path}")

    # Find the first non-empty line after the EXTINF
    pos = target_idx + 1
    while pos < len(lines) and lines[pos].strip() == "":
        pos += 1

    # collect existing consecutive comment lines (likely EXTVLCOPT) and optional URL
    start_replace = pos
    pos2 = pos
    while pos2 < len(lines) and lines[pos2].startswith("#"):
        pos2 += 1

    existing_url = None
    if pos2 < len(lines) and not lines[pos2].startswith("#") and lines[pos2].strip() != "":
        existing_url = lines[pos2].strip()
        end_replace = pos2 + 1
    else:
        end_replace = pos2

    # parse existing opts to determine whether a rewrite is necessary
    existing_ref = None
    existing_ua = None
    for i in range(start_replace, end_replace if end_replace <= len(lines) else len(lines)):
        ln = lines[i].strip()
        if ln.startswith("#EXTVLCOPT:http-referrer="):
            existing_ref = ln.split("=", 1)[1]
        if ln.startswith("#EXTVLCOPT:http-user-agent="):
            existing_ua = ln.split("=", 1)[1]

    # decide if we need to write: if URL differs, or if provided ref/user_agent differ from existing
    desired_ref = referrer
    desired_ua = user_agent

    url_changed = (existing_url is None) or (existing_url.strip() != new_url.strip())
    opts_changed = False
    if desired_ref is not None or desired_ua is not None:
        # compare only for provided values
        if desired_ref is not None and desired_ref != existing_ref:
            opts_changed = True
        if desired_ua is not None and desired_ua != existing_ua:
            opts_changed = True

    if not url_changed and not opts_changed:
        # nothing to change
        return False, existing_url

    # validate new url before writing
    if not _validate_url(new_url, referrer, user_agent):
        raise RuntimeError(f"Validation failed for URL: {new_url}")

    # Build replacement block: if ref/user-agent provided, insert exactly one of each; otherwise preserve existing opts
    insert_lines = []
    if desired_ref is not None:
        insert_lines.append(f"#EXTVLCOPT:http-referrer={desired_ref}")
    elif existing_ref is not None:
        insert_lines.append(f"#EXTVLCOPT:http-referrer={existing_ref}")
    if desired_ua is not None:
        insert_lines.append(f"#EXTVLCOPT:http-user-agent={desired_ua}")
    elif existing_ua is not None:
        insert_lines.append(f"#EXTVLCOPT:http-user-agent={existing_ua}")

    # perform write (backup then replace slice)
    if not dry_run:
        # write backup only when an explicit backup_dir is provided. If backup_dir
        # is None we will NOT create a backup (user requested no backups / deleted backups folder).
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            bak = backup_dir / (file_path.name + ".bak." + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
            if not bak.exists():
                bak.write_text(text, encoding="utf-8")
        # replace the existing comment+url block
        new_block = insert_lines + [new_url]
        lines[start_replace:end_replace] = new_block
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, existing_url

    # if we didn't find a URL, insert after the EXTINF line
    insert_pos = target_idx + 1
    if not dry_run:
        bak = file_path.with_name(file_path.name + ".bak." + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
        bak.write_text(text, encoding="utf-8")
        lines.insert(insert_pos, new_url)
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, help="Page URL to scrape for m3u8")
    parser.add_argument("--file", default="../data/iptv.m3u8", help="Path to iptv.m3u8 file (relative to scripts/)")
    parser.add_argument("--tvg", default="SPORT.TV2", help="tvg-id to replace (default: SPORT.TV2)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write file; just report")
    parser.add_argument("--backup-dir", default=None, help="Directory to write backups into (relative to scripts/). If omitted no backups will be created.")
    args = parser.parse_args()
    # resolve paths relative to scripts/
    base = Path(__file__).resolve().parent
    file_path = (base / args.file).resolve()
    backup_dir = (base / args.backup_dir).resolve() if args.backup_dir else None
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(3)

    print(f"Fetching page: {args.page}")
    try:
        found = find_m3u8_in_page(args.page)
    except Exception as e:
        print(f"Error fetching page: {e}")
        sys.exit(4)

    if not found:
        print("No .m3u8 URL found on page")
        sys.exit(5)

    print(f"Found candidate m3u8: {found}")

    try:
        changed, old = update_m3u_file(file_path, args.tvg, found, dry_run=args.dry_run, referrer=None, user_agent=None, backup_dir=backup_dir)
    except Exception as e:
        print(f"Error updating file: {e}")
        sys.exit(6)

    if not changed:
        print("File already contains the URL; no change made.")
        sys.exit(0)

    print(f"Updated {file_path} for {args.tvg}")
    if old:
        print(f"Replaced: {old}")


if __name__ == "__main__":
    main()
