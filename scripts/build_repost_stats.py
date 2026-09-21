#!/usr/bin/env python3
"""
Derive _data/repost-authors.json from the LinkedIn archive.

Usage: build_repost_stats.py [_data/linkedin-posts.json] [_data/repost-authors.json]

A post counts as a repost when its author is not williammilisic, which is the
same rule the archive pages already use. The figures travel with the archive
rather than being counted in Liquid, so the authors-with-sections list does
not have to walk every post for every author at build time.
"""
import json
import os
import re
import sys
import tempfile
import unicodedata

DEFAULT_ARCHIVE_PATH = os.path.join("_data", "linkedin-posts.json")
DEFAULT_DATA_PATH = os.path.join("_data", "repost-authors.json")
OWN_USERNAME = "williammilisic"
NON_SLUG = re.compile(r"[^a-z0-9]+")
WHITESPACE = re.compile(r"\s+")


class RepostStatsError(Exception):
    pass


def slugify(name):
    """An anchor for an author heading. Accents are folded rather than dropped so
    that two names differing only in accent do not collide."""
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(character for character in folded if not unicodedata.combining(character))
    return NON_SLUG.sub("-", ascii_only.lower()).strip("-")


def author_name(author):
    """What the archive already shows as the author. Keyed on the display name
    rather than the handle: a few reposted authors carry no handle in the data,
    and keying on that would count each of them as a separate person every time
    they appear."""
    author = author or {}
    name = " ".join(
        part for part in (author.get("first_name"), author.get("last_name")) if part
    ).strip()
    return name or author.get("username") or "Unknown"


def safe_https(url):
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return ""


def post_year(post):
    date = ((post.get("posted_at") or {}).get("date") or "")[:4]
    return date if date.isdigit() else ""


def snippet(text, words=15):
    """A short stand-in for a title. Reposted posts have no title of their own,
    and the full body is too long to list under an author heading."""
    text = WHITESPACE.sub(" ", (text or "").strip())
    if not text:
        return "(no text)"
    parts = text.split(" ")
    if len(parts) <= words:
        return text
    return " ".join(parts[:words]) + "…"


def collect_reposts(posts):
    reposts = []
    for post in posts:
        author = post.get("author") or {}
        if author.get("username") == OWN_USERNAME:
            continue
        year = post_year(post)
        if not year:
            raise RepostStatsError(
                "a reposted post has no readable year: %r" % (post.get("url") or post.get("full_urn"))
            )
        name = author_name(author)
        reposts.append({
            "author": name,
            "username": author.get("username") or "",
            "profile_url": safe_https(author.get("profile_url") or ""),
            "year": year,
            "date": ((post.get("posted_at") or {}).get("date") or "")[:10],
            "snippet": snippet(post.get("text")),
            "url": safe_https(post.get("url") or ""),
            "reactions": int(post.get("totalReactionCount") or 0),
            "comments": int(post.get("commentsCount") or 0),
        })
    return reposts


def summarise(reposts):
    years = {}
    authors = {}
    for entry in reposts:
        year = years.setdefault(entry["year"], {"year": entry["year"], "total": 0})
        year["total"] += 1
        bucket = authors.setdefault(entry["author"], {
            "name": entry["author"],
            "username": entry["username"],
            "profile_url": entry["profile_url"],
            "posts": [],
        })
        # Prefer a handle and profile link when any of the author's entries
        # carries one; earlier scrapes sometimes left them blank.
        if not bucket["username"] and entry["username"]:
            bucket["username"] = entry["username"]
        if not bucket["profile_url"] and entry["profile_url"]:
            bucket["profile_url"] = entry["profile_url"]
        bucket["posts"].append(entry)

    ordered_years = sorted(years.values(), key=lambda year: year["year"], reverse=True)
    ordered_authors = sorted(
        authors.values(),
        key=lambda author: (-len(author["posts"]), author["name"]),
    )

    top_authors = []
    used_slugs = {}
    for author in ordered_authors:
        count = len(author["posts"])
        if count < 2:
            continue
        slug = slugify(author["name"]) or "author"
        if slug in used_slugs:
            used_slugs[slug] += 1
            slug = "%s-%d" % (slug, used_slugs[slug])
        else:
            used_slugs[slug] = 1
        written = sorted(
            author["posts"],
            key=lambda entry: (entry["date"], entry["snippet"]),
            reverse=True,
        )
        top_authors.append({
            "name": author["name"],
            "username": author["username"],
            "profile_url": author["profile_url"],
            "count": count,
            "slug": slug,
            "posts": [
                {
                    "snippet": entry["snippet"],
                    "year": entry["year"],
                    "date": entry["date"],
                    "url": entry["url"],
                    "reactions": entry["reactions"],
                    "comments": entry["comments"],
                }
                for entry in written
            ],
        })

    return {
        "total": len(reposts),
        "authors": len(authors),
        "repeated_authors": len(top_authors),
        "first_year": min(years) if years else "",
        "last_year": max(years) if years else "",
        "busiest_year": max(ordered_years, key=lambda year: year["total"])["total"] if years else 0,
        "years": ordered_years,
        "top_authors": top_authors,
    }


def write_data(path, payload):
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, prefix=".reposts-", suffix=".json", delete=False
    ) as handle:
        handle.write(text)
        temporary_path = handle.name
    os.replace(temporary_path, path)


def main(argv):
    archive_path = argv[1] if len(argv) > 1 else DEFAULT_ARCHIVE_PATH
    data_path = argv[2] if len(argv) > 2 else DEFAULT_DATA_PATH

    try:
        with open(archive_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        posts = payload["data"]["posts"]
        if not isinstance(posts, list):
            raise RepostStatsError("archive posts are not a list")
        reposts = collect_reposts(posts)
    except (OSError, KeyError, TypeError, ValueError, RepostStatsError) as error:
        print("build_repost_stats: %s" % error, file=sys.stderr)
        return 1

    summary = summarise(reposts)
    write_data(data_path, {"summary": summary, "reposts": reposts})
    print("Reposts in the archive: %d" % summary["total"])
    print("Distinct authors: %d" % summary["authors"])
    print("Authors reposted more than once: %d" % summary["repeated_authors"])
    print("Years covered: %s to %s" % (summary["first_year"], summary["last_year"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
