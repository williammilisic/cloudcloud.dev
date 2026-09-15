#!/usr/bin/env python3
import json
import re
import os
from datetime import datetime

BOOKLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "booklist.md")
POSTS_PATH = os.path.join(os.path.dirname(__file__), "..", "_data", "linkedin-posts.json")

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

OWN_USERNAME = "williammilisic"

# A title and author are carved out of post text by the regexes below, so they
# arrive here as arbitrary text rather than as known-good values. Everything
# written into booklist.md is therefore constrained first: kramdown renders
# inline HTML in that file, which is what the <br/> tags in it rely on, so an
# unfiltered title would land on the books page as live markup.
MARKUP_CHARACTERS = re.compile(r"[<>&\[\]()`*_|\\\r\n\t]")
MAX_FIELD_LENGTH = 200

# Only a LinkedIn post permalink is ever a legitimate review link, so the url is
# matched against that shape rather than merely checked for a scheme.
SAFE_URL = re.compile(r"^https://(?:www\.)?linkedin\.com/[A-Za-z0-9._~:/?#@!$&'*+,;=%-]*$")

def clean_url(url):
    if not url:
        return ""
    # Strip tracking query parameters like ?utm_source=...
    return url.split("?")[0]

def safe_link(url):
    """Return the url only if it can stand as a markdown link destination."""
    if not url or not SAFE_URL.match(url):
        return ""
    return url

def safe_field(value):
    """Reduce a parsed title or author to plain text that renders as itself."""
    if not value:
        return ""
    collapsed = MARKUP_CHARACTERS.sub(" ", value)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    return collapsed[:MAX_FIELD_LENGTH].strip()

# Where a name ends. The patterns below let an author run through letters,
# spaces and periods, because names contain all three, so a captured name keeps
# going into whatever followed it in the post: "by Tae Kim. I couldn't help
# but..." yielded "Tae Kim. I couldn", and "by Jeffrey Pfeffer was that it was
# highly cynical" yielded the lot.
#
# Two things end a name. One is the sentence it sits in; the period after an
# initial ends nothing, so only a period following a whole word counts, which
# leaves "L. David Marquet" and "A.G. Lafley" intact. The other is a word that
# cannot be part of a name: prose is lower case, and names are not, apart from
# the few words that join two of them together.
SENTENCE_END = re.compile(r'(?<=[a-z]{2})[.!?](?:\s|$)')
JOINING_WORDS = {'and', '&', 'with', 'van', 'von', 'de', 'der', 'den', 'di', 'da', 'la', 'le'}
MAX_NAME_WORDS = 12


def trim_to_name(author):
    """Cut a captured author back to the part that can actually be a name.

    Returns an empty string when nothing in it can be, which is the honest
    answer for a capture like "two audiobooks": the caller skips the post and
    says so, rather than writing a sentence fragment into the list as a name.
    """
    if not author:
        return ''
    author = author.split('\n')[0]

    ends = SENTENCE_END.search(author)
    if ends:
        author = author[:ends.start()]

    kept = []
    for word in author.split()[:MAX_NAME_WORDS]:
        if word.lower().strip('.,') in JOINING_WORDS:
            kept.append(word)
            continue
        if not word[:1].isupper():
            break
        kept.append(word)

    # A name cannot begin or end on the word that joined it to another one.
    while kept and kept[0].lower().strip('.,') in JOINING_WORDS:
        kept.pop(0)
    while kept and kept[-1].lower().strip('.,') in JOINING_WORDS:
        kept.pop()

    return ' '.join(kept).strip(' .,')


def parse_title_author(text):
    clean_text = text.replace('”', '"').replace('“', '"').replace('’', "'").replace('‘', "'")
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    first_line = lines[0] if lines else ""
    
    title = None
    author = None
    
    # Check quotes in first 2 lines
    text_sample = " ".join(lines[:3])
    
    # 1. "I just finished [Author]'s [latest/new/classic] book, [Title]" or similar
    m = re.search(r'(?:finished|read|listened to)\s+([A-Z][a-zA-Z\u00C0-\u024F\s\.\-]+?)(?:\'s|\s+latest|\s+classic|\s+new|\s+book)*\s+(?:book,?\s+)?["\']([^"\']+)["\']', text_sample, re.IGNORECASE)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
        author = re.sub(r'^(?:listening to|the audiobook|audiobook|reading|read)\s+', '', author, flags=re.IGNORECASE).strip()
        return title, trim_to_name(author)

    # 2. "Just finished [Title] by [Author]"
    m = re.search(r'(?:finished|read|listened to)\s+(?:the\s+audiobook\s+|the\s+book\s+)?["\']([^"\']+)["\']\s+by\s+([A-Z][a-zA-Z\u00C0-\u024F\s\.\-]+)', text_sample, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip().split('\n')[0].split(',')[0].strip()
        return title, trim_to_name(author)

    # 3. "finished [Title] by [Author]" without quotes
    m = re.search(r'finished\s+([A-Z][a-zA-Z0-9\s:\-\?]+?)\s+by\s+([A-Z][a-zA-Z\u00C0-\u024F\s\.\-]+)', text_sample, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip().split('\n')[0].split(',')[0].strip()
        return title, trim_to_name(author)

    # 4. Fallback: extract title from quotes in first line
    quotes = re.findall(r'["\']([^"\']+)["\']', first_line)
    if quotes:
        title = quotes[0].strip()
        # Try finding "by Author"
        m_by = re.search(r'by\s+([A-Z][a-zA-Z\u00C0-\u024F\s\.\-]+)', first_line)
        if m_by:
            author = trim_to_name(m_by.group(1).strip())
            
    # 5. Fallback: First line title before colon/dash
    if not title and ":" in first_line:
        title = first_line.split(":")[0].strip()

    return title, author

def update_booklist():
    if not os.path.exists(BOOKLIST_PATH) or not os.path.exists(POSTS_PATH):
        print("Required files not found.")
        return False

    with open(BOOKLIST_PATH, "r", encoding="utf-8") as f:
        booklist_content = f.read()

    with open(POSTS_PATH, "r", encoding="utf-8") as f:
        posts_data = json.load(f)

    posts = posts_data.get("data", {}).get("posts", [])
    
    # Collect existing activity IDs and URLs from booklist.md
    existing_act_ids = set(re.findall(r'activity[-:](\d+)', booklist_content))
    
    new_entries = []

    for post in posts:
        # Preview text is cut off mid-sentence, so title/author parsing on it
        # yields mangled results. Wait for a full-text sync of these posts.
        if post.get("text_truncated"):
            continue

        # A repost is someone else's review, and this is a list of books I read,
        # so reposted text is never parsed and never reaches booklist.md.
        if (post.get("author") or {}).get("username") != OWN_USERNAME:
            continue

        url = clean_url(post.get("url", ""))
        text = post.get("text", "")
        date_str = post.get("posted_at", {}).get("date", "")

        act_id_m = re.search(r'activity[-:](\d+)', url)
        act_id = act_id_m.group(1) if act_id_m else ""

        # Check if already present in booklist.md
        if (act_id and act_id in existing_act_ids) or (url and url in booklist_content):
            continue

        lower = text.lower()
        is_book_review = (
            '#bookreview' in lower or 'bookreview' in lower or 'book review' in lower or
            'finished reading' in lower or 'finished listening' in lower or
            'finished the audiobook' in lower or 'recently finished' in lower or
            'just finished' in lower
        )

        if not is_book_review:
            continue

        title, author = parse_title_author(text)
        title = safe_field(title)
        author = safe_field(author)

        if not title or not author:
            print(f"Skipping unparsed book post: {date_str} - {url}")
            continue

        link = safe_link(url)
        if not link:
            print(f"Skipping book post with an unusable link: {date_str} - {url!r}")
            continue

        # Parse date
        dt = None
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            except Exception:
                pass

        if not dt:
            continue

        year_str = str(dt.year)
        month_name = MONTH_NAMES[dt.month]

        entry_md = f"* **{title}**\n<br/>By: {author}<br/>{month_name} {year_str} <br/>[LinkedIn review]({link})"
        new_entries.append((dt, year_str, month_name, title, author, link, entry_md))

    if not new_entries:
        print("No new book reviews found.")
        return False

    print(f"Found {len(new_entries)} new book reviews to add.")

    # Group by year
    for dt, year_str, month_name, title, author, url, entry_md in new_entries:
        year_header = f"## {year_str}"

        # The entry goes in through a function rather than a replacement string,
        # because re.sub reads backslashes in a replacement string as group
        # references: a title holding \1 would splice the heading into the entry,
        # and one holding \g<x> would abort the nightly run outright.
        if year_header in booklist_content:
            # Insert under year header
            pattern = rf"(## {year_str}\n\n)"
            booklist_content = re.sub(
                pattern, lambda m: f"{m.group(1)}{entry_md}\n\n", booklist_content, count=1
            )
        else:
            # Create new year section at top after first <br/>
            new_section = f"## {year_str}\n\n{entry_md}\n\n\n"
            booklist_content = re.sub(
                r"(<br/>\n)", lambda m: f"{m.group(1)}{new_section}", booklist_content, count=1
            )

    with open(BOOKLIST_PATH, "w", encoding="utf-8") as f:
        f.write(booklist_content)

    print("Successfully updated booklist.md.")
    return True

if __name__ == "__main__":
    update_booklist()
