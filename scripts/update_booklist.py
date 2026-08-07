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

def clean_url(url):
    if not url:
        return ""
    # Strip tracking query parameters like ?utm_source=...
    return url.split("?")[0]

def parse_title_author(text):
    clean_text = text.replace('”', '"').replace('“', '"').replace('’', "'").replace('‘', "'")
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    first_line = lines[0] if lines else ""
    
    title = None
    author = None
    
    # Check quotes in first 2 lines
    text_sample = " ".join(lines[:3])
    
    # 1. "I just finished [Author]'s [latest/new/classic] book, [Title]" or similar
    m = re.search(r'(?:finished|read|listened to)\s+([A-Z][a-zA-Z\s\.\-]+?)(?:\'s|\s+latest|\s+classic|\s+new|\s+book)*\s+(?:book,?\s+)?["\']([^"\']+)["\']', text_sample, re.IGNORECASE)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
        author = re.sub(r'^(?:listening to|the audiobook|audiobook|reading|read)\s+', '', author, flags=re.IGNORECASE).strip()
        return title, author

    # 2. "Just finished [Title] by [Author]"
    m = re.search(r'(?:finished|read|listened to)\s+(?:the\s+audiobook\s+|the\s+book\s+)?["\']([^"\']+)["\']\s+by\s+([A-Z][a-zA-Z\s\.\-]+)', text_sample, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip().split('\n')[0].split(',')[0].strip()
        return title, author

    # 3. "finished [Title] by [Author]" without quotes
    m = re.search(r'finished\s+([A-Z][a-zA-Z0-9\s:\-\?]+?)\s+by\s+([A-Z][a-zA-Z\s\.\-]+)', text_sample, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip().split('\n')[0].split(',')[0].strip()
        return title, author

    # 4. Fallback: extract title from quotes in first line
    quotes = re.findall(r'["\']([^"\']+)["\']', first_line)
    if quotes:
        title = quotes[0].strip()
        # Try finding "by Author"
        m_by = re.search(r'by\s+([A-Z][a-zA-Z\s\.\-]+)', first_line)
        if m_by:
            author = m_by.group(1).strip()
            
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

        if not title or not author:
            print(f"Skipping unparsed book post: {date_str} - {url}")
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

        entry_md = f"* **{title}**\n<br/>By: {author}<br/>{month_name} {year_str} <br/>[LinkedIn review]({url})"
        new_entries.append((dt, year_str, month_name, title, author, url, entry_md))

    if not new_entries:
        print("No new book reviews found.")
        return False

    print(f"Found {len(new_entries)} new book reviews to add.")

    # Group by year
    for dt, year_str, month_name, title, author, url, entry_md in new_entries:
        year_header = f"## {year_str}"

        if year_header in booklist_content:
            # Insert under year header
            pattern = rf"(## {year_str}\n\n)"
            replacement = f"\\1{entry_md}\n\n"
            booklist_content = re.sub(pattern, replacement, booklist_content, count=1)
        else:
            # Create new year section at top after first <br/>
            new_section = f"## {year_str}\n\n{entry_md}\n\n\n"
            booklist_content = re.sub(r"(<br/>\n)", rf"\1{new_section}", booklist_content, count=1)

    with open(BOOKLIST_PATH, "w", encoding="utf-8") as f:
        f.write(booklist_content)

    print("Successfully updated booklist.md.")
    return True

if __name__ == "__main__":
    update_booklist()
