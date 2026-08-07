# cloudcloud.dev LinkedIn posts by comments

Back to [main](../index.md).

<br/>

<!-- markdownlint-disable MD033 -->
{% assign published_posts = site.data.linkedin-posts.data.posts %}

{% include linkedin-nav.html %}

<!-- Archive posts have no engagement data, so they get their own bucket instead of counting as 0 -->
{% assign known_posts = published_posts | where_exp: "p", "p.stats" %}
{% assign unknown_posts = published_posts | where_exp: "p", "p.stats == nil" %}
{% assign ranges_order = "100+,10-99,<10,Unknown" | split: "," %}
{% assign bucket_slugs = "100-plus,10-99,under-10,unknown" | split: "," %}
{% comment %}
Buckets that have a page of their own. Same guard as the year strip, so
a bucket can never link at a page that is not there.
{% endcomment %}
{% assign bucket_pages = "100-plus,10-99,under-10,unknown" | split: "," %}

<!-- Comments cloud -->
<div class="tag-list">
  {% for range in ranges_order %}
   {%- assign bucket_slug = bucket_slugs[forloop.index0] %}
   <a href="#{{ bucket_slug }}" class="btn btn-primary tag-btn">
    <i class="fas fa-comments" aria-hidden="true"></i>&nbsp;{{ range | escape }}&nbsp;
   </a>
  {% endfor %}
</div>

<div id="full-tags-list">
  {% for range in ranges_order %}
   {%- assign bucket_slug = bucket_slugs[forloop.index0] %}
   {%- if bucket_slug == "unknown" %}
   {%- assign posts_count = unknown_posts.size %}
   {%- assign bucket_href = "unknown.html" %}
   {%- else %}
   {%- assign bucket_href = "comments-" | append: bucket_slug | append: ".html" %}
   {% assign posts_count = 0 %}
   {% for post in known_posts %}
    {% assign tally = post.commentsCount | default: 0 %}
    {% assign in_range = false %}
    {% if bucket_slug == "100-plus" and tally >= 100 %}
      {% assign in_range = true %}
    {% elsif bucket_slug == "10-99" and tally >= 10 and tally < 100 %}
      {% assign in_range = true %}
    {% elsif bucket_slug == "under-10" and tally < 10 %}
      {% assign in_range = true %}
    {% endif %}
    {% if in_range %}
      {% assign posts_count = posts_count | plus: 1 %}
    {% endif %}
   {% endfor %}
   {%- endif %}
   <h3 id="{{ bucket_slug }}" class="linked-section">
    <i class="fas fa-comments" aria-hidden="true"></i>
    &nbsp;{{ range | escape }}&nbsp;({{ posts_count }} posts)
   </h3>
   <div class="post-list">
    <div class="tag-entry">
     {%- assign has_page = true %}
     {%- if bucket_pages %}
     {%- unless bucket_pages contains bucket_slug %}
     {%- assign has_page = false %}
     {%- endunless %}
     {%- endif %}
     {%- if has_page %}
     <a href="{{ bucket_href }}">Read all {{ posts_count }} posts in this range</a>
     {%- else %}
     <span>No page for this range yet</span>
     {%- endif %}
    </div>
   </div>
  {% endfor %}
</div>
