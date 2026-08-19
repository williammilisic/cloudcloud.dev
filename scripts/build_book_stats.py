#!/usr/bin/env python3
"""
Derive _data/books.json from booklist.md.

Usage: build_book_stats.py [booklist.md] [_data/books.json]

booklist.md stays the thing a human reads and edits; this only reads it. Every
bullet in the list has to parse, because a stats page that quietly counts 119 of
121 books is worse than one that refuses to build, so an entry this cannot read
fails the run with the line quoted rather than being skipped.
"""
import json
import os
import re
import sys
import tempfile

DEFAULT_BOOKLIST_PATH = "booklist.md"
DEFAULT_DATA_PATH = os.path.join("_data", "books.json")

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# One entry is two lines: a bolded title, optionally followed by a parenthesised
# note such as (reread), then a details line. The details line is hand written
# across eight years, so the separator is allowed to be <br> or <br/>, and the
# spacing around the author and the month is allowed to be anything.
TITLE_LINE = re.compile(r"^\* \*\*(?P<title>.+?)\*\*\s*(?:\((?P<note>[^)]*)\))?\s*$")
BREAK = r"<br\s*/?>"
DETAIL_LINE = re.compile(
    r"^\s*" + BREAK + r"\s*By:\s*(?P<author>.*?)\s*" + BREAK +
    r"\s*(?P<month>[A-Za-z]+)?\s*(?P<year>\d{4})\s*(?P<rest>.*)$"
)
REVIEW_LINK = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)\s]+)")
YEAR_HEADING = re.compile(r"^##\s*(?P<year>\d{4})\s*$")
REREAD_NOTE = re.compile(r"re-?(read|listen)", re.I)


class BookListError(Exception):
    pass


def split_authors(author):
    """A single field holds one to three people, joined however the entry felt
    like joining them, so the same person counts once however they were listed."""
    parts = re.split(r"\s*(?:,|&|\band\b)\s*", author)
    return [part.strip(" .") for part in parts if part.strip(" .")]


def parse_entries(text):
    lines = text.split("\n")
    entries = []
    heading_year = None
    for index, line in enumerate(lines):
        heading = YEAR_HEADING.match(line)
        if heading:
            heading_year = heading.group("year")
            continue

        title_match = TITLE_LINE.match(line)
        if not title_match:
            if line.startswith("* **"):
                raise BookListError(
                    "line %d could not be read as a book title: %r" % (index + 1, line)
                )
            continue

        detail = DETAIL_LINE.match(lines[index + 1]) if index + 1 < len(lines) else None
        if not detail:
            raise BookListError(
                "the entry %r on line %d has no readable author and date line"
                % (title_match.group("title"), index + 1)
            )

        month = detail.group("month") or ""
        if month and month not in MONTHS:
            raise BookListError(
                "the entry %r on line %d gives its month as %r"
                % (title_match.group("title"), index + 1, month)
            )

        links = [
            {"label": link.group("label"), "url": link.group("url")}
            for link in REVIEW_LINK.finditer(detail.group("rest"))
        ]
        note = title_match.group("note") or ""
        entries.append({
            "title": title_match.group("title").strip(),
            "author": detail.group("author").strip(),
            "authors": split_authors(detail.group("author")),
            "month": month,
            "year": detail.group("year"),
            "section_year": heading_year,
            "note": note,
            "reread": bool(REREAD_NOTE.search(note)),
            "reviewed": bool(links),
            "links": links,
        })
    return entries


def check_complete(text, entries):
    bullets = len(re.findall(r"^\* \*\*", text, re.M))
    if bullets != len(entries):
        raise BookListError(
            "booklist.md holds %d entries but only %d were read" % (bullets, len(entries))
        )


def summarise(entries):
    years = {}
    for entry in entries:
        year = years.setdefault(entry["year"], {"year": entry["year"], "total": 0, "reviewed": 0})
        year["total"] += 1
        if entry["reviewed"]:
            year["reviewed"] += 1

    authors = {}
    for entry in entries:
        for name in entry["authors"]:
            authors[name] = authors.get(name, 0) + 1

    ordered_authors = sorted(authors.items(), key=lambda pair: (-pair[1], pair[0]))
    ordered_years = sorted(years.values(), key=lambda year: year["year"], reverse=True)
    return {
        "total": len(entries),
        "reviewed": sum(1 for entry in entries if entry["reviewed"]),
        "rereads": sum(1 for entry in entries if entry["reread"]),
        "authors": len(authors),
        "first_year": min(years) if years else "",
        "last_year": max(years) if years else "",
        "busiest_year": max(ordered_years, key=lambda year: year["total"])["total"] if years else 0,
        "years": ordered_years,
        "top_authors": [
            {"name": name, "count": count} for name, count in ordered_authors if count > 1
        ],
    }


def write_data(path, payload):
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, prefix=".books-", suffix=".json", delete=False
    ) as handle:
        handle.write(text)
        temporary_path = handle.name
    os.replace(temporary_path, path)


def main(argv):
    booklist_path = argv[1] if len(argv) > 1 else DEFAULT_BOOKLIST_PATH
    data_path = argv[2] if len(argv) > 2 else DEFAULT_DATA_PATH

    try:
        with open(booklist_path, "r", encoding="utf-8") as handle:
            text = handle.read()
        entries = parse_entries(text)
        check_complete(text, entries)
    except (OSError, BookListError) as error:
        print("build_book_stats: %s" % error, file=sys.stderr)
        return 1

    summary = summarise(entries)
    write_data(data_path, {"summary": summary, "books": entries})
    print("Books read from booklist.md: %d" % summary["total"])
    print("With a linked review: %d" % summary["reviewed"])
    print("Distinct authors: %d" % summary["authors"])
    print("Years covered: %s to %s" % (summary["first_year"], summary["last_year"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
