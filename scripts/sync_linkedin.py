#!/usr/bin/env python3
"""
Fetch LinkedIn UGC posts for the configured author and write posts older than CUTOFF_DAYS
to the 'posts/' directory as markdown files.

Environment variables (set in GitHub Secrets or workflow env):
- LINKEDIN_ACCESS_TOKEN : OAuth2 Bearer token with UGC and read permissions
- LINKEDIN_AUTHOR_URN  : The author URN, e.g. 'urn:li:person:AAAAAAAA'
- TARGET_DIR            : directory to write files (default: posts)
- CUTOFF_DAYS           : cutoff in days (default: 365)
"""
import os
import sys
import time
import requests
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import re

LINKEDIN_API = "https://api.linkedin.com/v2/ugcPosts"
TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR = os.environ.get("LINKEDIN_AUTHOR_URN")
TARGET_DIR = os.environ.get("TARGET_DIR", "posts")
CUTOFF_DAYS = int(os.environ.get("CUTOFF_DAYS", "365"))

if not TOKEN or not AUTHOR:
    print("Missing LINKEDIN_ACCESS_TOKEN or LINKEDIN_AUTHOR_URN environment variables.", file=sys.stderr)
    sys.exit(2)

HEADERS = {a
    "Authorization": f"Bearer {TOKEN}",
    "X-Restli-Protocol-Version": "2.0.0",
    "Accept": "application/json",
}

Path(TARGET_DIR).mkdir(parents=True, exist_ok=True)

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9\-]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s[:60] or hashlib.sha1(s.encode()).hexdigest()[:10]

def extract_text(item):
    try:
        sc = item.get("specificContent", {})
        share = sc.get("com.linkedin.ugc.ShareContent", {})
        commentary = share.get("shareCommentary", {})
        text = commentary.get("text")
        if text:
            return text
        share_text = share.get("shareContent", {}).get("text")
        if share_text:
            return share_text
    except Exception:
        pass
    return ""

def extract_media(item):
    media = []
    try:
        sc = item.get("specificContent", {})
        share = sc.get("com.linkedin.ugc.ShareContent", {})
        content_entities = share.get("media", []) or share.get("shareMediaCategory") and share.get("media", [])
        if isinstance(content_entities, list):
            for m in content_entities:
                if isinstance(m, dict):
                    url = m.get("media") or m.get("originalUrl") or m.get("contentUrl")
                    if url:
                        media.append(url)
                    if "status" in m and "id" in m:
                        media.append(json.dumps(m))
    except Exception:
        pass
    return media

def to_markdown(item):
    created_ms = item.get("created", {}).get("time")
    created_dt = datetime.fromtimestamp(created_ms/1000, tz=timezone.utc) if created_ms else None
    text = extract_text(item) or ""
    media = extract_media(item)
    urn = item.get("id") or item.get("entity")
    md = []
    md.append("---")
    md.append(f"linkedin_urn: \"{urn}\"")
    md.append(f"created_at: \"{created_dt.isoformat() if created_dt else ''}\"")
    md.append("---\n")
    md.append(text + "\n")
    if media:
        md.append("\n\n<!-- Media -->\n")
        for m in media:
            md.append(f"- {m}\n")
    return "\n".join(md), created_dt, urn

def fetch_posts(start=0, count=50):
    params = {
        "q": "authors",
        "authors": AUTHOR,
        "start": start,
        "count": count,
    }
    resp = requests.get(LINKEDIN_API, headers=HEADERS, params=params, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"LinkedIn API error {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()

def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
    start = 0
    count = 50
    total_fetched = 0
    created_count = 0

    while True:
        data = fetch_posts(start=start, count=count)
        elements = data.get("elements", [])
        if not elements:
            break
        for el in elements:
            total_fetched += 1
            created_ms = el.get("created", {}).get("time")
            if not created_ms:
                continue
            created_dt = datetime.fromtimestamp(created_ms/1000, tz=timezone.utc)
            if created_dt <= cutoff:
                md, created_dt_out, urn = to_markdown(el)
                id_for_name = urn or el.get("id") or str(created_ms)
                short = hashlib.sha1(id_for_name.encode()).hexdigest()[:8]
                slug = slugify((el.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get("text") or "")[:40])
                date_part = created_dt_out.strftime("%Y-%m-%d")
                filename = f"{date_part}_{slug or 'post'}_{short}.md"
                out_path = Path(TARGET_DIR) / filename
                if any(urn in p.read_text(errors='ignore') for p in Path(TARGET_DIR).glob("*.md")):
                    continue
                out_path.write_text(md, encoding="utf-8")
                created_count += 1
        start += len(elements)
        if len(elements) < count:
            break
        time.sleep(1)

    print(f"Fetched {total_fetched} items, wrote {created_count} post files to '{TARGET_DIR}'")

if __name__ == "__main__":
    main()
````markdown name=README_LINKEDIN_SYNC.md
```markdown
# Sync LinkedIn posts older than 1 year

This provides a GitHub Actions workflow + Python script to fetch your LinkedIn UGC posts and create markdown files for all posts older than 1 year (configurable). The workflow runs monthly and commits the generated files to a branch so you can review or merge them.

Required secrets (set in the repository settings → Secrets and variables → Actions → New repository secret):
- LINKEDIN_ACCESS_TOKEN: OAuth2 access token with the required LinkedIn permissions (UGC read, shares, etc.). Tokens from LinkedIn OAuth need appropriate scopes (e.g., r_ugc). Use a long-lived token or refresh flow for production.
- LINKEDIN_AUTHOR_URN: Your LinkedIn author URN, e.g. `urn:li:person:XXXXXXXX`.

How it works:
1. The action runs `scripts/sync_linkedin.py`.
2. The script pages through LinkedIn UGC posts for the provided author, filters posts older than `CUTOFF_DAYS` (default 365), and writes one markdown file per post into `posts/`.
3. The workflow commits and pushes changes to branch `sync/linkedin-old-posts`.

Customizations:
- Change the schedule cron in `.github/workflows/sync-linkedin.yml`.
- Change cutoff by setting `CUTOFF_DAYS` env in the workflow (e.g., `730` for 2 years).
- Change storage target (S3, Google Drive) by modifying the script to upload instead of committing files.

Notes and gotchas:
- LinkedIn API limits and scopes: ensure your app/token has the right permissions to read UGC/shares.
- The script uses a simple heuristic to extract text and media; you may need to adapt it for complex post formats (video, multiple images, reshared content).
- For production reliability consider implementing token refresh, better pagination error handling, retries, and rate-limit handling.
