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
{% for scope in version.scope_status %}|{{scope.ref}}|{{scope.summary}}|{{scope.labels | join(',')}}|{{scope.milestones | join(',')}}|
{% endfor %}

## Release Candidates

|tag|date|status|content|
|-|-|-|-|
{% for tag in version.release_candidates %}|{{tag.tag}}|{{tag.date}}|{{tag.status}}|{{tag.content | join('<br>')}}|
{% endfor %}
{% endfor %}
