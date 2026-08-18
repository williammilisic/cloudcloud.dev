#!/usr/bin/env python3
"""
Restore full post text from an official LinkedIn data export.

Usage: import_shares_export.py <export.zip|Shares.csv> [_data/linkedin-posts.json]
       import_shares_export.py <export.zip> --dry-run
       import_shares_export.py <export.zip> --add-missing 2014-01-01

The script does two jobs, the second only when --add-missing is given.

Restoring text. The scraper behind the nightly sync caps older posts at 400
characters and drops the line breaks around the cut, so much of the archive is
stored as previews. The export carries the complete text, but it identifies
posts by share and ugcPost urns while the archive uses activity urns, so the
two cannot be joined on id. Rows are matched on the moment the post was
published instead, which the export records in UTC and the archive in local
time, and every match is then confirmed by checking that the stored preview
really is a prefix of the exported text.

Adding missing posts. The scraper never saw several hundred posts that the
export does hold. Deciding which rows are genuinely absent cannot rest on
publication time, because a scheduled post is stamped when it was written in
the export and when it went out in the archive, hours apart. A row therefore
counts as already archived when any id in its permalink appears in the archive
or when its text matches a stored post, and only rows failing both tests become
new entries. The export carries no engagement figures, so these posts are
written without a stats object and the pages render them as having no
engagement data rather than as having none.

Writing is delegated to merge_linkedin_posts.py so that the guards protecting
the nightly sync apply here too.
"""
import collections
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_ARCHIVE_PATH = os.path.join("_data", "linkedin-posts.json")
MERGE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "merge_linkedin_posts.py")

# The export and the scraper record the same instant a second or two apart.
TIMESTAMP_TOLERANCE_SECONDS = 1
# How much of the stored preview has to line up before a match is believed.
PREFIX_CHARS = 150
# The archive writes the wall clock time the post went out, not UTC.
LOCAL_ZONE = ZoneInfo("Europe/Stockholm")
# Short posts repeat too easily to be compared on their opening characters.
MIN_CHARS_TO_COMPARE = 40
# The same words this close together are one post that went out twice.
DOUBLE_POST_SECONDS = 600

EXPORT_URN = re.compile(r"urn:li:(share|ugcPost|groupPost):([\w-]+)")
ARCHIVE_ID = re.compile(r"(?:activity|share|ugcPost)[:-](\d+)")

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

# Jekyll reads data files with a YAML parser, and YAML rejects control
# characters that JSON is happy to carry, so one stray byte fails the whole site
# build. Text out of the export occasionally holds a character from the C1
# block, which is cp1252 punctuation that lost its decoding on the way, so those
# are put back rather than dropped.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def repair_control_characters(text):
    def readable(match):
        character = match.group()
        if "\x80" <= character <= "\x9f":
            try:
                decoded = bytes([ord(character)]).decode("cp1252")
            except (UnicodeDecodeError, ValueError):
                return ""
            return "" if CONTROL_CHARACTERS.match(decoded) else decoded
        return ""

    return CONTROL_CHARACTERS.sub(readable, text or "")


def unescape_line_breaks(text):
    return LINE_BREAK_ESCAPE.sub("\n", text or "")


def export_text(row):
    return repair_control_characters(unescape_line_breaks(row.get("ShareCommentary") or ""))


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
            "text": export_text(row),
            "text_truncated": False,
        })
    return payload, skipped


def export_urn(row):
    """The kind and id of the post a permalink points at, as the export writes
    it: percent encoded, and naming shares and ugcPosts rather than activities."""
    link = urllib.parse.unquote(row.get("ShareLink") or "")
    found = EXPORT_URN.search(link)
    return (found.group(1), found.group(2)) if found else (None, None)


def archive_identifiers(posts):
    identifiers = set()
    for post in posts:
        urn = post.get("urn")
        if isinstance(urn, dict):
            for value in urn.values():
                if value:
                    identifiers.add(str(value))
        for field in (post.get("full_urn"), urn if isinstance(urn, str) else "", post.get("url")):
            identifiers.update(ARCHIVE_ID.findall(field or ""))
    return identifiers


def archive_seconds(posts):
    seconds = set()
    for post in posts:
        try:
            seconds.add(int(post["posted_at"]["timestamp"]) // 1000)
        except (KeyError, TypeError, ValueError):
            continue
    return seconds


def archive_texts(posts):
    """Stored post text, whole for exact comparison and grouped by opening for
    the previews, so a row can be recognised however it was cut."""
    whole, openings = set(), collections.defaultdict(list)
    for post in posts:
        text = comparable(post.get("text"))
        if not text:
            continue
        whole.add(text)
        if len(text) >= MIN_CHARS_TO_COMPARE:
            openings[text[:MIN_CHARS_TO_COMPARE]].append(text)
    return whole, openings


def already_archived(identifier, second, text, identifiers, seconds, stored_texts):
    if identifier and identifier in identifiers:
        return True
    # Two posts never share a second, so the same second is the same post even
    # when its wording has since been edited. Scheduled posts drift the other
    # way, which leaves them looking new rather than wrongly matched.
    if second in seconds:
        return True
    whole, openings = stored_texts
    candidate = comparable(text)
    if not candidate:
        return False
    # A one line post repeats too easily to be judged on its opening, so short
    # text has to match a stored post outright.
    if candidate in whole:
        return True
    if len(candidate) < MIN_CHARS_TO_COMPARE:
        return False
    # Either side may be the shorter one: the archive holds previews cut at 400
    # characters, while the export holds posts shorter than that in full.
    for stored in openings.get(candidate[:MIN_CHARS_TO_COMPARE], ()):
        shared = min(len(stored), len(candidate), PREFIX_CHARS)
        if stored[:shared] == candidate[:shared]:
            return True
    return False


def author_of_archive(posts):
    """The author block the archive already uses for its own posts, so imported
    posts carry the same name, headline and picture as their neighbours."""
    seen = collections.Counter()
    for post in posts:
        author = post.get("author")
        if isinstance(author, dict) and author.get("username"):
            seen[json.dumps(author, ensure_ascii=False, sort_keys=True)] += 1
    if not seen:
        raise SystemExit("the archive holds no author block to copy")
    return json.loads(seen.most_common(1)[0][0])


def new_post(row, kind, identifier, author, text):
    published = published_second(row.get("Date"))
    moment = datetime.fromtimestamp(published, timezone.utc).astimezone(LOCAL_ZONE)
    return {
        "urn": {
            "activity_urn": None,
            "share_urn": identifier if kind == "share" else None,
            "ugcPost_urn": identifier if kind == "ugcPost" else None,
        },
        "full_urn": "urn:li:%s:%s" % (kind, identifier),
        "posted_at": {
            "date": moment.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": published * 1000,
        },
        "text": text,
        "url": "https://www.linkedin.com/feed/update/urn:li:%s:%s" % (kind, identifier),
        "post_type": "regular",
        "author": author,
        "text_truncated": False,
    }


def build_new_posts(rows, posts, since):
    identifiers = archive_identifiers(posts)
    seconds = archive_seconds(posts)
    stored_texts = archive_texts(posts)
    author = author_of_archive(posts)
    additions, seen, taken, skipped = [], set(), {}, collections.Counter()
    for row in rows:
        date = (row.get("Date") or "")[:19]
        if not date or date < since:
            skipped["published before %s" % since] += 1
            continue
        kind, identifier = export_urn(row)
        second = published_second(row.get("Date"))
        if not identifier or second is None:
            skipped["no usable permalink or date"] += 1
            continue
        text = export_text(row)
        if not text.strip():
            skipped["no commentary to publish"] += 1
            continue
        if already_archived(identifier, second, text, identifiers, seconds, stored_texts):
            skipped["already in the archive"] += 1
            continue
        if identifier in seen:
            # The export repeats some posts verbatim, permalink and all.
            skipped["repeated in the export"] += 1
            continue
        # The same words years apart are two posts; minutes apart they are one
        # post submitted twice.
        previous = taken.get(comparable(text))
        if previous is not None and abs(second - previous) <= DOUBLE_POST_SECONDS:
            skipped["submitted twice over"] += 1
            continue
        seen.add(identifier)
        taken[comparable(text)] = second
        additions.append(new_post(row, kind, identifier, author, text))
    return additions, skipped


def main(argv):
    argv = list(argv)
    dry_run = "--dry-run" in argv
    if dry_run:
        argv.remove("--dry-run")
    since = None
    if "--add-missing" in argv:
        position = argv.index("--add-missing")
        if position + 1 >= len(argv):
            raise SystemExit("--add-missing needs a date, for instance 2014-01-01")
        since = argv[position + 1]
        del argv[position:position + 2]
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

    if since:
        additions, not_added = build_new_posts(rows, posts, since)
        print("posts missing from the archive since %s: %d" % (since, len(additions)))
        for reason, count in sorted(not_added.items()):
            if count:
                print("  not added, %s: %d" % (reason, count))
        payload = payload + additions

    if not payload:
        print("nothing to restore")
        return 0

    unreadable = [post for post in payload if CONTROL_CHARACTERS.search(post.get("text") or "")]
    if unreadable:
        raise SystemExit("%d posts still carry control characters, which would fail the site "
                         "build rather than show up as a broken page" % len(unreadable))

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
