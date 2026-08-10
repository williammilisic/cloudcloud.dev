"""Publish the contents of scratch.md into dated posts under _posts/.

Content written without a heading becomes an entry for PUBLISH_DATE (the date of
the triggering commit). A `## <date>` heading starts an entry for that date
instead, which allows backdating. Writing to a date that already has a post
appends to it rather than replacing it, so a day can hold several entries.
"""

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = REPO / "scratch.md"
POSTS = REPO / "_posts"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_NUM = {m: i for i, m in enumerate(MONTHS, 1)}

HEADING = re.compile(r"^##\s+(.*\S)\s*$")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

TEMPLATE = """<!--
Scratch space. Anything written below is published as a dated entry the next
time this file is committed to main, then this file is emptied again.

Write plain markdown for an entry dated today:

    * A thought worth keeping.

Or open with a date heading to backdate an entry, or to write several at once:

    ## 9 August 2026
    * Something from yesterday.
-->
"""


def parse_heading_date(text):
    """Return a date from '10 August 2026' or '2026-08-10', else None."""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if iso:
        y, m, d = (int(g) for g in iso.groups())
        try:
            return date(y, m, d)
        except ValueError:
            return None
    parts = text.split()
    if len(parts) == 3 and parts[1] in MONTH_NUM and parts[0].isdigit() and parts[2].isdigit():
        try:
            return date(int(parts[2]), MONTH_NUM[parts[1]], int(parts[0]))
        except ValueError:
            return None
    return None


def publish_date():
    raw = os.environ.get("PUBLISH_DATE", "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return datetime.utcnow().date()


def split_entries(body, default_day):
    """Split scratch text into (date, content) pairs."""
    lines = body.split("\n")
    marks = [i for i, l in enumerate(lines) if HEADING.match(l)]
    entries = []

    lead = lines[: marks[0]] if marks else lines
    if "\n".join(lead).strip():
        entries.append((default_day, "\n".join(lead).strip("\n")))

    for n, start in enumerate(marks):
        end = marks[n + 1] if n + 1 < len(marks) else len(lines)
        label = HEADING.match(lines[start]).group(1)
        day = parse_heading_date(label)
        if day is None:
            raise SystemExit(
                "Could not read a date from heading '## %s'. Use a form like "
                "'## 10 August 2026' or '## 2026-08-10'." % label
            )
        content = "\n".join(lines[start + 1:end]).strip("\n")
        if content.strip():
            entries.append((day, content))
    return entries


def title_for(day):
    return "%d %s %d" % (day.day, MONTHS[day.month - 1], day.year)


def write_entry(day, content):
    """Create the post for `day`, or append to it when it already exists."""
    path = POSTS / ("%s-notes.md" % day.isoformat())
    if path.exists():
        existing = path.read_text(encoding="utf-8").rstrip("\n")
        path.write_text(existing + "\n\n" + content + "\n", encoding="utf-8")
        return path, "appended to"

    title = title_for(day)
    front = [
        "---",
        "layout: default",
        'title: "%s"' % title,
        "date: %s" % day.isoformat(),
        "permalink: /%04d/%02d/%02d/" % (day.year, day.month, day.day),
        'original_heading: "%s"' % title,
        "---",
    ]
    path.write_text("\n".join(front) + "\n\n" + content + "\n", encoding="utf-8")
    return path, "created"


def main():
    if not SCRATCH.exists():
        print("No scratch.md, nothing to publish")
        return 0

    raw = SCRATCH.read_text(encoding="utf-8")
    body = COMMENT.sub("", raw).strip("\n")
    if not body.strip():
        print("Scratch is empty, nothing to publish")
        return 0

    POSTS.mkdir(exist_ok=True)
    entries = split_entries(body, publish_date())
    if not entries:
        print("Scratch holds no publishable content")
        return 0

    for day, content in entries:
        path, how = write_entry(day, content)
        print("%s %s (%d characters)" % (how, path.relative_to(REPO), len(content)))

    SCRATCH.write_text(TEMPLATE, encoding="utf-8")
    print("Published %d entr%s and cleared the scratch" %
          (len(entries), "y" if len(entries) == 1 else "ies"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
