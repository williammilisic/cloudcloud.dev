#!/usr/bin/env python3
"""
Restore full post text from an official LinkedIn data export.

Usage: import_shares_export.py <export.zip|Shares.csv> [_data/linkedin-posts.json]
       import_shares_export.py <export.zip> --dry-run

The scraper behind the nightly sync caps older posts at 400 characters and
drops the line breaks around the cut, so much of the archive is stored as
previews. The export carries the complete text, but it identifies posts by
share and ugcPost urns while the archive uses activity urns, so the two cannot
be joined on id. Rows are matched on the moment the post was published instead,
which the export records in UTC and the archive in local time, and every match
is then confirmed by checking that the stored preview really is a prefix of the
exported text. Anything that fails either test is left alone.

Writing is delegated to merge_linkedin_posts.py so that the guards protecting
the nightly sync apply here too.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone

DEFAULT_ARCHIVE_PATH = os.path.join("_data", "linkedin-posts.json")
MERGE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "merge_linkedin_posts.py")

# The export and the scraper record the same instant a second or two apart.
TIMESTAMP_TOLERANCE_SECONDS = 1
# How much of the stored preview has to line up before a match is believed.
PREFIX_CHARS = 150

SMART_CHARACTERS = (
    ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
    ("\u201e", '"'), ("\u2013", "-"), ("\u2014", "-"), ("\xa0", ""),
)

# The export escapes the line breaks inside ShareCommentary by wrapping every
# newline in a straight double quote on each side, so a paragraph break arrives
# as '"\n"' and a blank line as '"\n""\n"'. Authored quotation marks sit beside
# those artefacts rather than replacing them, so taking exactly one quote from
# each side of a newline strips the escaping and leaves real quotes alone.
LINE_BREAK_ESCAPE = re.compile(r'"\n"')


def unescape_line_breaks(text):
    return LINE_BREAK_ESCAPE.sub("\n", text or "")


def comparable(text):
    """Reduce text to what both sources agree on: the scraper renders hashtags
    as "hashtag#name" and the export quotes CSV fields, so neither survives."""
    text = unicodedata.normalize("NFKC", text or "").replace("hashtag#", "#")
    for fancy, plain in SMART_CHARACTERS:
        text = text.replace(fancy, plain)
    return re.sub(r"\s+", "", re.sub(r"[\"']", "", text))


def read_shares(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist()
                     if os.path.basename(n).startswith("Shares") and n.endswith(".csv")]
            if not names:
                raise SystemExit("%s holds no Shares csv; request the larger export" % path)
            with archive.open(names[0]) as handle:
                rows = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))
        return rows
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def published_second(value):
    try:
        moment = datetime.strptime((value or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


def index_by_second(rows):
    index = {}
    for row in rows:
        second = published_second(row.get("Date"))
        if second is not None:
            index.setdefault(second, []).append(row)
    return index


def find_row(post, index):
    timestamp = post.get("posted_at", {}).get("timestamp")
    try:
        second = int(timestamp) // 1000
    except (TypeError, ValueError):
        return None
    for offset in range(-TIMESTAMP_TOLERANCE_SECONDS, TIMESTAMP_TOLERANCE_SECONDS + 1):
        rows = index.get(second + offset)
        if not rows:
            continue
        stored = comparable(post.get("text"))
        for row in rows:
            if comparable(row.get("ShareCommentary")).startswith(stored[:PREFIX_CHARS]):
                return row
    return None


def build_payload(posts, index):
    payload, skipped = [], {"no matching export row": 0, "text does not agree": 0}
    for post in posts:
        if not post.get("text_truncated"):
            continue
        row = find_row(post, index)
        if row is None:
            timestamp = post.get("posted_at", {}).get("timestamp")
            second = int(timestamp) // 1000 if str(timestamp).isdigit() else None
            near = any(index.get((second or 0) + offset)
                       for offset in range(-TIMESTAMP_TOLERANCE_SECONDS,
                                           TIMESTAMP_TOLERANCE_SECONDS + 1))
            skipped["text does not agree" if near else "no matching export row"] += 1
            continue
        payload.append({
            "full_urn": post.get("full_urn"),
            "urn": post.get("urn"),
            "posted_at": post.get("posted_at"),
            "author": post.get("author"),
            "url": post.get("url"),
            "text": unescape_line_breaks(row.get("ShareCommentary")),
            "text_truncated": False,
        })
    return payload, skipped


def main(argv):
    argv = list(argv)
    dry_run = "--dry-run" in argv
    if dry_run:
        argv.remove("--dry-run")
    if not argv:
        raise SystemExit(__doc__.strip())
    export_path = argv[0]
    archive_path = argv[1] if len(argv) > 1 else DEFAULT_ARCHIVE_PATH

    with open(archive_path, encoding="utf-8") as handle:
        posts = json.load(handle)["data"]["posts"]
    rows = read_shares(export_path)
    payload, skipped = build_payload(posts, index_by_second(rows))

    truncated = sum(1 for post in posts if post.get("text_truncated"))
    print("archive holds %d posts, %d of them stored as previews" % (len(posts), truncated))
    print("export holds %d rows" % len(rows))
    print("previews matched to the export: %d" % len(payload))
    for reason, count in sorted(skipped.items()):
        if count:
            print("  left alone, %s: %d" % (reason, count))
    if not payload:
        print("nothing to restore")
        return 0

    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump({"success": True, "message": "", "data": {"posts": payload}},
                  handle, ensure_ascii=False)
        handle.close()
        if dry_run:
            print("dry run, %s left untouched" % archive_path)
            return 0
        return subprocess.call([sys.executable, MERGE_SCRIPT, handle.name, archive_path])
    finally:
        os.unlink(handle.name)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
