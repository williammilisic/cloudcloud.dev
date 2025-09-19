# cloudcloud.dev LinkedIn posts

Back to [main](../index.md).

<br/>

<!-- markdownlint-disable MD033 -->
{% assign published_posts = site.data.linkedin-posts.data.posts %}

<!-- Buttons for ordering LinkedIn posts -->
<div class="list-filters">
  <a href="linkedin.html" class="list-filter">All ({{ published_posts.size }})</a>
  <a href="year.html" class="list-filter">By Year</a>
  <a href="reactions.html" class="list-filter">By Reactions</a>
  <a href="comments.html" class="list-filter">By Comments</a>
</div>

<div class="linkedin-posts-container post-preview">
  {% for post in site.data.linkedin-posts.data.posts %}
  <a href="{{ post.url }}" target="_blank" class="linkedin-post-link">
   <div class="linkedin-post-card">
    <div class="linkedin-post-text">
      <h4 class="linkedin-post-title">{{ post.text | truncatewords: 100 }}</h4>
      <p class="linkedin-post-description">
       Posted on {{ post.posted_at.date | date: "%b %-d, %Y" }}
      </p>
      <p class="linkedin-post-stats">
       <span><i class="fas fa-thumbs-up"></i> Reactions: {{ post.totalReactionCount | default: 0 }}</span> |
       <span><i class="fas fa-comments"></i> Comments: {{ post.commentsCount | default: 0 }}</span> |
       <span><i class="fas fa-retweet"></i> Repost: {{ post.repostsCount | default: 0 }}</span>
      </p>
    </div>
   </div>
  </a>
  {% endfor %}
</div>
