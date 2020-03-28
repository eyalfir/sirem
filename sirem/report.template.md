# TOC

{% for version in status %}
[{{version.tag}}](#{{version.tag | replace(" ", "-") | replace(".", "") }})
{% endfor %}

{% for version in status %}
# {{version.tag}}

## milestones

|milestone|date|
|-|-|
{% for milestone in version.milestones %}|{{milestone.name}}|{{milestone.date}}|
{% endfor %}

## scope

|ref|summary|labels|milestones|
|-|-|-|-|
{% for scope in version.scope_status %}|{{content_link(scope.ref, options)}}|{{scope.summary}}|{{map(label_to_emoji, scope.labels) | join('<br>')}}|{{map(label_to_emoji, scope.milestones) | join('<br>')}}|
{% endfor %}

## Release Candidates

|tag|date|status|content|
|-|-|-|-|
{% for tag in version.release_candidates %}|{{tag.tag}}|{{tag.date}}|{{tag.status}}|{{map(partial(content_link, options=options), tag.content) | join('<br>')}}|
{% endfor %}
{% endfor %}
