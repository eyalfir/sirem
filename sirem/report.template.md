# TOC

{% macro content_link(ref, options) -%}
    {% if options.jira_baseurl -%}
        [{{ref}}]({{options.jira_baseurl}}/browse/{{ref}})
    {%- else -%}
        {{ref}}
    {% endif %}
{%- endmacro %}

{% for version in status %}
[{{version.tag}}](#{{version.tag | replace(" ", "-") | replace(".", "") }})
{% endfor %}

{% for version in status %}
# {{version.tag}}

{% if version.milestones %}
## milestones

|milestone|date|
|-|-|
{% for milestone in version.milestones %}|{{milestone.name}}|{{milestone.date}}|
{% endfor %}
{% endif %}

{% if version.scope_status %}
## scope

|ref|summary|labels|milestones|
|-|-|-|-|
{% for scope in version.scope_status -%}
|{{content_link(scope.ref, options)}}|{{scope.summary}}|{{map(label_to_emoji, scope.labels) | join('<br>')}}|{{map(label_to_emoji, scope.milestones) | join('<br>')}}|
{% endfor %}
{% endif %}

{% if version.release_candidates %}
## Release Candidates

|tag|date|status|content|
|-|-|-|-|
{% for tag in version.release_candidates -%}
|{{tag.tag}}|{{tag.date}}|{{tag.status}}|{% for content in tag.content.keys() %}{{ content_link(content, options) }}{% if tag.content[content] %} - {{tag.content[content]}}{% endif %}<br>{% endfor %}|
{% endfor %}
{% endif %}

{% endfor %}
