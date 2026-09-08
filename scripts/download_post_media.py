#!/usr/bin/env python3
"""
Save the images attached to archived LinkedIn posts before their links expire.

Usage: download_post_media.py [--archive PATH] [--into DIR] [--dry-run]

LinkedIn serves post media from a CDN behind a signed link that carries its own
expiry in the "e" query parameter, roughly a month out. Once that moment passes
the link returns 403 and the image is gone as far as this archive is concerned;
there is no way to re-sign it from here. The nightly sync stores whatever link
was current when it ran, so an image is only recoverable during the window
between the sync that captured it and that expiry.

This copies the still-live ones onto disk, where they stop expiring. It is safe
to re-run: anything already saved is left alone, so the usual way to use it is
to run it after each sync and let it pick up whatever is new.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ARCHIVE = os.path.join("_data", "linkedin-posts.json")
DEFAULT_DIRECTORY = os.path.join("assets", "images", "linkedin")
MANIFEST_NAME = "manifest.json"

# Nothing here should ever write outside the media directory, so the name is
# built from the post date and a hash of the link rather than from anything the
# scrape supplies.
SAFE_NAME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{10}\.(jpg|png|gif|mp4)$")

ALLOWED_HOSTS = ("media.licdn.com", "dms.licdn.com")
EXTENSION_FOR = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "video/mp4": "mp4",
}
MAX_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 60
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36"


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE)
    parser.add_argument("--into", default=DEFAULT_DIRECTORY)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be fetched without fetching it")
    parser.add_argument("--from-links", metavar="FILE",
                        help="take links from a file of 'activity id<tab>link' lines "
                             "instead of from the archive, for links gathered by hand "
                             "from a signed in session")
    return parser.parse_args(argv)


def media_links(archive_path):
    """Every distinct media link in the archive, with the post it belongs to.

    The shape of the media field varies between scrapes, so this walks whatever
    is there rather than assuming a particular nesting.
    """
    with open(archive_path, encoding="utf-8") as handle:
        posts = json.load(handle)["data"]["posts"]

    found = {}

    def walk(node, post):
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and url.startswith("https://") and url not in found:
                found[url] = {
                    "posted": (post.get("posted_at") or {}).get("date", "")[:10],
                    "post_url": (post.get("url") or "").split("?")[0],
                }
            for value in node.values():
                walk(value, post)
        elif isinstance(node, list):
            for value in node:
                walk(value, post)

    for post in posts:
        if post.get("media"):
            walk(post["media"], post)
    return found


def links_from_file(links_path, archive_path):
    """Links gathered elsewhere, matched back to the posts they belong to.

    A link whose signature has expired cannot be re-signed from here, but the
    post itself still renders for someone signed in, and the page it renders
    carries a fresh link to the same picture. Those are what this reads, as
    lines of 'activity id<tab>link', so that they land in the same store under
    the same rules as everything the sync saves itself.
    """
    with open(archive_path, encoding="utf-8") as handle:
        posts = json.load(handle)["data"]["posts"]

    by_activity = {}
    for post in posts:
        url = post.get("url") or ""
        found = re.search(r"activity[:-](\d+)", url)
        if found:
            by_activity[found.group(1)] = {
                "posted": (post.get("posted_at") or {}).get("date", "")[:10],
                "post_url": url.split("?")[0],
            }

    links = {}
    unmatched = 0
    with open(links_path, encoding="utf-8") as handle:
        for line in handle:
            if "\t" not in line:
                continue
            activity_id, url = line.strip().split("\t", 1)
            about = by_activity.get(activity_id)
            if not about:
                unmatched += 1
                continue
            links.setdefault(url, about)
    if unmatched:
        print("lines with no matching post: %d" % unmatched)
    return links


ASSET_IN_PATH = re.compile(r"/dms/image/v2/([^/]+)/")


def stable_key(url):
    """What identifies a picture, whatever link happens to point at it.

    Two things vary for one picture. The query string is re-signed every time
    the sync runs, so it says nothing about which picture this is. The path then
    names a rendering rather than the picture: the same photograph is served as
    feedshare-shrink_800, feedshare-shrink_1280 and feedshare-image-high-res,
    which are different bytes and so slip past a check on content.

    What does not vary is the asset id in the middle of the path. Keying on that
    is what keeps one photograph from being saved once per size it is offered
    in. Anything without one, a video playlist for instance, falls back to the
    path, which is stable enough for those.
    """
    parsed = urllib.parse.urlparse(url)
    found = ASSET_IN_PATH.search(parsed.path)
    return found.group(1) if found else parsed.path


def expires_at(url):
    """The moment the signature stops being accepted, if the link carries one."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "e" not in query:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(query["e"][0]), datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def host_allowed(url):
    return urllib.parse.urlparse(url).hostname in ALLOWED_HOSTS


def load_manifest(directory):
    path = os.path.join(directory, MANIFEST_NAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_manifest(directory, manifest):
    path = os.path.join(directory, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def fetch(url):
    """The bytes behind a link, refusing anything that is not a modest image."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type not in EXTENSION_FOR:
            raise ValueError("unexpected content type %r" % content_type)
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_BYTES:
            raise ValueError("declared size %s is beyond the limit" % declared)
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("body is beyond the limit")
    if not body:
        raise ValueError("body is empty")
    return body, EXTENSION_FOR[content_type]


def main(argv):
    options = parse_arguments(argv)
    if options.from_links:
        links = links_from_file(options.from_links, options.archive)
    else:
        links = media_links(options.archive)
    now = datetime.datetime.now(datetime.timezone.utc)

    manifest = load_manifest(options.into)
    already = set()
    for entry in manifest.values():
        # Recomputed rather than read back, so that entries written before the
        # key became the asset id are still recognised as held.
        already.add(stable_key(entry["url"]))
        already.update(stable_key(seen) for seen in entry.get("also_at", []))
    known_content = {entry["sha256"]: name for name, entry in manifest.items() if entry.get("sha256")}

    live = []
    expired = 0
    for url, about in links.items():
        if stable_key(url) in already:
            continue
        if not host_allowed(url):
            continue
        when = expires_at(url)
        if when is not None and when <= now:
            expired += 1
            continue
        live.append((url, about, when))

    live.sort(key=lambda item: item[2] or now)

    print("media links in the archive : %d" % len(links))
    print("already saved              : %d" % len(already))
    print("links already expired      : %d" % expired)
    print("still live, to fetch       : %d" % len(live))
    if live and live[0][2]:
        print("soonest to expire          : %s (in %d days)"
              % (live[0][2].strftime("%Y-%m-%d %H:%M UTC"), (live[0][2] - now).days))

    if options.dry_run or not live:
        return 0

    if not os.path.isdir(options.into):
        os.makedirs(options.into)

    saved = 0
    failed = 0
    duplicates = 0
    for url, about, _ in live:
        digest = hashlib.sha256(stable_key(url).encode("utf-8")).hexdigest()[:10]
        try:
            body, extension = fetch(url)
        except (urllib.error.URLError, ValueError, OSError) as error:
            failed += 1
            print("  could not fetch %s...: %s" % (url[:60], error))
            continue

        # The same picture is sometimes reachable by more than one path, so the
        # bytes are checked as well as the path before another copy is written.
        content = hashlib.sha256(body).hexdigest()
        if content in known_content:
            # Noting the other path it answers on is what stops this being
            # downloaded again on every run just to be thrown away again.
            held = manifest[known_content[content]]
            aliases = held.setdefault("also_at", [])
            if stable_key(url) not in aliases:
                aliases.append(stable_key(url))
                aliases.sort()
            duplicates += 1
            continue

        known_content[content] = "%s-%s.%s" % (about["posted"] or "undated", digest, extension)

        name = "%s-%s.%s" % (about["posted"] or "undated", digest, extension)
        if not SAFE_NAME.match(name):
            failed += 1
            print("  refusing to write an unexpected name %r" % name)
            continue

        with open(os.path.join(options.into, name), "wb") as handle:
            handle.write(body)
        manifest[name] = {
            "url": url,
            "path": stable_key(url),
            "sha256": content,
            "posted": about["posted"],
            "post_url": about["post_url"],
            "bytes": len(body),
            "saved": now.strftime("%Y-%m-%d"),
        }
        saved += 1

    save_manifest(options.into, manifest)
    total = sum(entry["bytes"] for entry in manifest.values())
    print("saved                      : %d" % saved)
    print("already held under another link: %d" % duplicates)
    print("failed                     : %d" % failed)
    print("held on disk now           : %d files, %.1f MB"
          % (len(manifest), total / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
