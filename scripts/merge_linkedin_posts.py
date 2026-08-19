#!/usr/bin/env python3
"""
Merge a freshly fetched LinkedIn API payload into the stored post archive.

Usage: merge_linkedin_posts.py [fetched.json] [_data/linkedin-posts.json]

The merge is additive and keyed on post identity: archived posts are never
dropped, and a stored field is only overwritten when the incoming payload
carries a non-empty value for it. The script exits non-zero without touching
the archive when the fetched payload is malformed or when the merge would
reduce the number of archived posts.
"""
import copy
import json
import os
import re
import sys
import tempfile

DEFAULT_FETCHED_PATH = "linkedin-posts.json"
DEFAULT_ARCHIVE_PATH = os.path.join("_data", "linkedin-posts.json")

# Jekyll reads this archive with a YAML parser, and YAML rejects control
# characters that JSON carries happily, so a single stray byte in a fetched post
# fails the whole site build after the commit has already landed. Tab, newline
# and carriage return are the ones YAML allows, so they are left alone.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

DERIVED_COUNTS = (
    ("commentsCount", "comments"),
    ("totalReactionCount", "total_reactions"),
    ("repostsCount", "reposts"),
)


class MergeError(Exception):
    pass


def is_empty(value):
    return value is None or (isinstance(value, (str, list, dict, tuple)) and len(value) == 0)


def as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def repair_control_characters(text):
    """Put back the cp1252 punctuation that lost its decoding upstream, and drop
    anything else the YAML parser would refuse."""
    def readable(match):
        character = match.group()
        if "\x80" <= character <= "\x9f":
            try:
                decoded = bytes([ord(character)]).decode("cp1252")
            except (UnicodeDecodeError, ValueError):
                return ""
            return "" if CONTROL_CHARACTERS.match(decoded) else decoded
        return ""

    return CONTROL_CHARACTERS.sub(readable, text)


def repair_values(value):
    if isinstance(value, str):
        return repair_control_characters(value)
    if isinstance(value, dict):
        return {key: repair_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repair_values(item) for item in value]
    return value


def find_control_characters(value, path="post"):
    if isinstance(value, str):
        return [path] if CONTROL_CHARACTERS.search(value) else []
    if isinstance(value, dict):
        found = []
        for key, item in value.items():
            found.extend(find_control_characters(item, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, item in enumerate(value):
            found.extend(find_control_characters(item, f"{path}[{index}]"))
        return found
    return []


def identity_keys(post):
    keys = []
    full_urn = post.get("full_urn")
    if isinstance(full_urn, str) and full_urn:
        keys.append(("full_urn", full_urn))
    posted_at = post.get("posted_at")
    if isinstance(posted_at, dict):
        timestamp = posted_at.get("timestamp")
        if isinstance(timestamp, (int, float, str)) and not isinstance(timestamp, bool):
            keys.append(("timestamp", timestamp))
    return keys


def timestamp_of(post):
    posted_at = post.get("posted_at")
    if not isinstance(posted_at, dict):
        return 0
    timestamp = as_int(posted_at.get("timestamp"))
    return timestamp if timestamp is not None else 0


def without_whitespace(text):
    return "".join(text.split())


def prefer_fetched_text(stored, fetched):
    stored_text = stored.get("text")
    fetched_text = fetched.get("text")
    if not isinstance(fetched_text, str) or not fetched_text:
        return False
    if not isinstance(stored_text, str) or not stored_text:
        return True
    if fetched.get("text_truncated") and not stored.get("text_truncated"):
        return False
    # The API preview strips the line breaks it truncates around, so the
    # prefix test that separates a truncation from an edit ignores whitespace.
    if len(fetched_text) < len(stored_text):
        if without_whitespace(stored_text).startswith(without_whitespace(fetched_text)):
            return False
    return True


def merge_value(stored_value, fetched_value):
    if is_empty(fetched_value):
        return stored_value
    if isinstance(stored_value, dict) and isinstance(fetched_value, dict):
        merged = dict(stored_value)
        for key, value in fetched_value.items():
            if key in merged:
                merged[key] = merge_value(merged[key], value)
            elif not is_empty(value):
                merged[key] = value
        return merged
    return fetched_value


def merge_post(stored, fetched):
    merged = copy.deepcopy(stored)
    take_fetched_text = prefer_fetched_text(stored, fetched)
    for key, value in fetched.items():
        if key in ("text", "text_truncated"):
            continue
        if key in merged:
            merged[key] = merge_value(merged[key], value)
        elif not is_empty(value):
            merged[key] = value
    if take_fetched_text:
        merged["text"] = fetched["text"]
        if "text_truncated" in fetched:
            merged["text_truncated"] = fetched["text_truncated"]
        else:
            merged.pop("text_truncated", None)
    return merged


def apply_derived_counts(post):
    # Posts archived without engagement data keep their existing shape instead
    # of gaining fabricated zero counts, which the templates render as
    # "engagement data unavailable".
    stats = post.get("stats")
    if not isinstance(stats, dict):
        return
    for field, source in DERIVED_COUNTS:
        count = as_int(stats.get(source))
        if count is not None:
            post[field] = count


def validate_payload(payload, label):
    if not isinstance(payload, dict):
        raise MergeError(f"{label} is not a JSON object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MergeError(f"{label} has no 'data' object")
    posts = data.get("posts")
    if not isinstance(posts, list):
        raise MergeError(f"{label} has no 'data.posts' list")
    for index, post in enumerate(posts):
        if not isinstance(post, dict):
            raise MergeError(f"{label} post {index} is not a JSON object")
        if not isinstance(post.get("posted_at"), dict):
            raise MergeError(f"{label} post {index} has no 'posted_at' object")
        if not identity_keys(post):
            raise MergeError(
                f"{label} post {index} has neither 'full_urn' nor 'posted_at.timestamp'"
            )
    return posts


def load_payload(path, label):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return validate_payload(payload, label)


def check_not_destructive(stored_posts, merged_posts):
    if len(merged_posts) < len(stored_posts):
        raise MergeError(
            f"merge would reduce the archive from {len(stored_posts)} to {len(merged_posts)} posts"
        )
    merged_by_key = {}
    for post in merged_posts:
        for key in identity_keys(post):
            merged_by_key.setdefault(key, post)
    for post in stored_posts:
        match = None
        for key in identity_keys(post):
            if key in merged_by_key:
                match = merged_by_key[key]
                break
        if match is None:
            raise MergeError(f"stored post {identity_keys(post)} is missing from the merge result")
        if isinstance(post.get("stats"), dict) and not isinstance(match.get("stats"), dict):
            raise MergeError(f"stored post {identity_keys(post)} would lose its stats object")


def check_readable(posts):
    for post in posts:
        found = find_control_characters(post)
        if found:
            raise MergeError(
                "post %s still carries control characters at %s, which would fail the site "
                "build after the commit rather than show up as a broken page"
                % (identity_keys(post), ", ".join(found))
            )


def merge_archives(stored_posts, fetched_posts):
    merged_posts = [copy.deepcopy(post) for post in stored_posts]
    positions = {}
    for position, post in enumerate(merged_posts):
        for key in identity_keys(post):
            positions.setdefault(key, position)

    added = 0
    updated = 0
    for fetched in fetched_posts:
        position = None
        for key in identity_keys(fetched):
            if key in positions:
                position = positions[key]
                break
        if position is None:
            merged_posts.append(copy.deepcopy(fetched))
            for key in identity_keys(fetched):
                positions.setdefault(key, len(merged_posts) - 1)
            added += 1
            continue
        merged = merge_post(merged_posts[position], fetched)
        if merged != merged_posts[position]:
            updated += 1
        merged_posts[position] = merged
        for key in identity_keys(merged):
            positions.setdefault(key, position)

    for post in merged_posts:
        apply_derived_counts(post)
    merged_posts.sort(key=timestamp_of, reverse=True)
    check_not_destructive(stored_posts, merged_posts)
    check_readable(merged_posts)
    return merged_posts, added, updated


def write_archive(path, posts):
    payload = {"success": True, "message": "", "data": {"posts": posts}}
    # The archive stores non-ASCII characters raw, so escaping them here would
    # rewrite every accented post and bury the nightly diff.
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, prefix=".merge-", suffix=".json", delete=False
    ) as handle:
        handle.write(text)
        temporary_path = handle.name
    os.replace(temporary_path, path)


def fail(message):
    print(f"merge_linkedin_posts: {message}", file=sys.stderr)
    sys.exit(1)


def main(argv):
    fetched_path = argv[1] if len(argv) > 1 else DEFAULT_FETCHED_PATH
    archive_path = argv[2] if len(argv) > 2 else DEFAULT_ARCHIVE_PATH

    try:
        fetched_posts = load_payload(fetched_path, f"fetched payload '{fetched_path}'")
    except (OSError, ValueError, MergeError) as error:
        fail(f"{error}; the archive was left untouched")

    fetched_posts = [repair_values(post) for post in fetched_posts]

    stored_posts = []
    if os.path.exists(archive_path):
        try:
            stored_posts = load_payload(archive_path, f"archive '{archive_path}'")
        except (OSError, ValueError, MergeError) as error:
            fail(f"{error}; the archive was left untouched")

    try:
        merged_posts, added, updated = merge_archives(stored_posts, fetched_posts)
    except MergeError as error:
        fail(f"{error}; the archive was left untouched")

    write_archive(archive_path, merged_posts)
    print(f"Posts in archive before merge: {len(stored_posts)}")
    print(f"Number of new entries added: {added}")
    print(f"Number of existing entries updated: {updated}")
    print(f"Posts in archive after merge: {len(merged_posts)}")


if __name__ == "__main__":
    main(sys.argv)
