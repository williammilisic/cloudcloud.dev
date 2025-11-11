# Sync LinkedIn posts older than 1 year

This provides a GitHub Actions workflow + Python script to fetch your LinkedIn UGC posts and create markdown files for all posts older than 1 year (configurable). The workflow runs monthly and commits the generated files to a branch so you can review or merge them.

Required secrets (set in the repository settings -> Secrets):
- LINKEDIN_ACCESS_TOKEN: OAuth2 access token with the required LinkedIn permissions (UGC read, shares, etc.). Tokens from LinkedIn OAuth need appropriate scopes (r_liteprofile, r_ugc, w_member_social if posting, etc.). Use a long-lived token or refresh flow for production.
- LINKEDIN_AUTHOR_URN: Your LinkedIn author URN, e.g. `urn:li:person:XXXXXXXX`.

How it works:
1. The action runs `scripts/sync_linkedin.py`.
2. The script pages through the LinkedIn UGC posts for the provided author, filters posts older than 365 days (CUTOFF_DAYS), and writes one markdown file per post into `posts/`.
3. The workflow commits and pushes changes to branch `sync/linkedin-old-posts`.

Customizations:
- Change the schedule cron in `.github/workflows/sync-linkedin.yml`.
- Change cutoff by setting CUTOFF_DAYS env in the workflow (e.g., 730 for 2 years).
- Change storage target (S3, Google Drive) by modifying the script to upload instead of committing files.

Notes and gotchas:
- LinkedIn API limits and scopes: ensure your app/token has the right permissions to read UGC/shares.
- The script uses a simple heuristic to extract text and media; you may need to adapt it for complex post formats (video, multiple images, reshared content).
- For production reliability consider implementing token refresh, better pagination error handling, retries, and rate-limit handling.

If you'd like, I can:
- Adapt the script to sync to S3 instead of committing to the repo.
- Add token refresh (OAuth) flow or instructions for creating a long-lived token.
- Harden parsing for more LinkedIn post types (videos, reshared content, documents).
- Create a PR that adds these files to your repository and configures the workflow.
