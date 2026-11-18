# LinkedIn archive sync

Daily automation keeps the LinkedIn post archive, book reviews, and related stats in sync on `main`.

## Workflow

[`.github/workflows/update-linkedin-posts.yml`](.github/workflows/update-linkedin-posts.yml) runs every day at 00:00 UTC (and on `workflow_dispatch`).

It:

1. Fetches recent profile posts from RapidAPI
2. Merges them into [`_data/linkedin-posts.json`](_data/linkedin-posts.json) via [`scripts/merge_linkedin_posts.py`](scripts/merge_linkedin_posts.py)
3. Downloads new post images via [`scripts/download_post_media.py`](scripts/download_post_media.py) (CDN links expire in roughly 30 days)
4. Syncs book reviews into [`booklist.md`](booklist.md) via [`scripts/update_booklist.py`](scripts/update_booklist.py)
5. Rebuilds book and repost stats
6. Commits and pushes when anything changed

## Required secret

- `RAPIDAPI_LINKEDIN_DATA_API_KEY` — API key for the RapidAPI LinkedIn scraper used by the fetch step

## Related scripts

| Script | Role |
| --- | --- |
| `merge_linkedin_posts.py` | Additive merge into the JSON archive |
| `download_post_media.py` | Save images under `assets/images/linkedin/` |
| `update_booklist.py` | Pull book-review activity into `booklist.md` |
| `build_book_stats.py` / `build_repost_stats.py` | Rebuild derived figures |
| `import_shares_export.py` | Optional one-off: restore full text (and missing posts) from an official LinkedIn data export |

## Manual runs

- Re-run the sync: Actions → **Update LinkedIn Posts & Booklist** → Run workflow
- After hand-editing `booklist.md`: Actions → **Refresh Book Stats**, or run `scripts/build_book_stats.py` locally
