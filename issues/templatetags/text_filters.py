from django import template

register = template.Library()

@register.filter
def underscore_to_space(value):
    if not value:
        return value
    return str(value).replace("_", " ")