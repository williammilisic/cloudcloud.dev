---
layout: default
title: cloudcloud.dev
---
# cloudcloud.dev
[RSS]({{ '/feed.xml' | relative_url }})
[Books List](booklist.md) | [Podcasts List](podcastlist.md) | [LinkedIn profile](https://linkedin.com/in/williammilisic) | [LinkedIn posts]({{ '/linkedin/' | relative_url }})

> Cloud Cloud Dot Dev is about things, topics and aha-moments I encounter on a daily basis that I think may be interesting for saving and that also may be interesting for others to learn about or discover.
<br/>

{% for post in site.posts %}
## [{{ post.title }}]({{ post.url | relative_url }})
{{ post.content }}
{% endfor %}
