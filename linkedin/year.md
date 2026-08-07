# cloudcloud.dev LinkedIn posts by year

Back to [main](../index.md).

<br/>

<!-- markdownlint-disable MD033 -->
{% assign published_posts = site.data.linkedin-posts.data.posts %}

{% include linkedin-nav.html %}

{% assign date_format = site.date_format | default: "%B %-d, %Y" %}
{% assign years_list = "" | split: "" %}
{% for post in site.data.linkedin-posts.data.posts %}
{% assign post_year = post.posted_at.date | date: "%Y" %}
{% unless years_list contains post_year %}
{% assign years_list = years_list | push: post_year %}
{% endunless %}
{% endfor %}
{% assign years_list = years_list | sort %}

<!-- Years cloud -->
<div class="tag-list">
     {% for year in years_list %}
     <a href="#{{- year -}}" class="btn btn-primary tag-btn"><i class="fas fa-calendar-alt" aria-hidden="true"></i>&nbsp;{{- year -}} &nbsp;</a>
     {% endfor %}
</div>

{% assign reverse_years_list = years_list | reverse %}

<div id="full-tags-list">
     {% for year in reverse_years_list %}
     {% assign posts_count = 0 %}
     {% for post in site.data.linkedin-posts.data.posts %}
          {% assign post_year = post.posted_at.date | date: "%Y" %}
          {% if post_year == year %}
                {% assign posts_count = posts_count | plus: 1 %}
          {% endif %}
     {% endfor %}
     <h3 id="{{- year -}}" class="linked-section">
          <i class="fas fa-calendar-alt" aria-hidden="true"></i>
          &nbsp;{{- year -}}&nbsp;({{ posts_count }} posts)
     </h3>
     <div class="post-list">
          {% comment %}
          archive_years is set by the nav include above. Only years that already
          have a page of their own are listed there, so this link cannot 404.
          {% endcomment %}
          <div class="tag-entry">
                {%- if archive_years contains year %}
                <a href="{{ year }}.html">Read all {{ posts_count }} posts from {{ year }}</a>
                {%- else %}
                <span>No page for {{ year }} yet</span>
                {%- endif %}
          </div>
     </div>
     {% endfor %}
</div>
