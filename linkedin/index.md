# cloudcloud.dev LinkedIn posts

Back to [main](../index.md).

<br/>

<!-- markdownlint-disable MD033 -->
{% assign published_posts = site.data.linkedin-posts.data.posts %}

<!-- Buttons for ordering LinkedIn posts -->
<div class="list-filters">
  <a href="index.html" class="list-filter">All ({{ published_posts.size }})</a>
  <a href="year.html" class="list-filter">By Year</a>
  <a href="reactions.html" class="list-filter">By Reactions</a>
  <a href="comments.html" class="list-filter">By Comments</a>
</div>

<style>
.linkedin-posts-container .linkedin-post-card {
  padding: 1.75em 0;
  border-bottom: 1px solid #dcdcdc;
}
.linkedin-posts-container .linkedin-post-card:last-child {
  border-bottom: 0;
}
.linkedin-post-body {
  line-height: 1.55;
  margin-bottom: 0.9em;
}
.linkedin-post-description,
.linkedin-post-stats {
  font-size: 0.85em;
  color: #6d6d6d;
  margin: 0.3em 0 0 0;
}
</style>

<div class="linkedin-posts-container post-preview">
  {% for post in site.data.linkedin-posts.data.posts %}
   <div class="linkedin-post-card">
    <div class="linkedin-post-text">
      <div class="linkedin-post-body">{{ post.text | escape | newline_to_br | strip_newlines }}{%- if post.text_truncated %}&hellip;{%- endif %}</div>
      <p class="linkedin-post-description">
       Posted on {{ post.posted_at.date | date: "%b %-d, %Y" }} ·
       <a href="{{ post.url | escape }}" target="_blank" rel="noopener noreferrer" class="linkedin-post-link">Read on LinkedIn</a>
       {%- if post.text_truncated %}
       · preview only, full text unavailable
       {%- endif %}
      </p>
      <p class="linkedin-post-stats">
       {%- if post.stats %}
       <span><i class="fas fa-thumbs-up"></i> Reactions: {{ post.totalReactionCount | default: 0 }}</span> |
       <span><i class="fas fa-comments"></i> Comments: {{ post.commentsCount | default: 0 }}</span> |
       <span><i class="fas fa-retweet"></i> Repost: {{ post.repostsCount | default: 0 }}</span>
       {%- else %}
       <span>engagement data unavailable</span>
       {%- endif %}
      </p>
    </div>
   </div>
  {% endfor %}
</div>
