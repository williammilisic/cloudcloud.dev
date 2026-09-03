# cloudcloud.dev LinkedIn posts

Back to [main](../).

<br/>

<!-- markdownlint-disable MD033 -->
{% include linkedin-nav.html %}

Search the full text of every post in the archive. The archive is downloaded
once and matched in your browser, so nothing you type is sent anywhere. Put a
phrase in quotes to keep its words together; several words outside quotes are
all required.

<form class="archive-search" role="search">
  <label for="search-query">Search the archive</label>
  <input type="search" id="search-query" name="q" autocomplete="off" spellcheck="false"
         placeholder="platform engineering" disabled>
</form>

<p class="search-status" id="search-status" role="status" aria-live="polite">Loading the archive&hellip;</p>

<div class="linkedin-posts-container post-preview" id="search-results" data-index="{{ '/linkedin/search-index.json' | relative_url }}"></div>

<p class="search-more"><button type="button" id="search-more" hidden>Show more results</button></p>

<noscript>
<p>Searching happens in the browser, so it needs JavaScript. Without it, the year
links above still lead to the whole archive.</p>
</noscript>

<script src="{{ '/assets/js/linkedin-search.js' | relative_url }}" defer></script>
