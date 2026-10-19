from django import template

register = template.Library()


@register.filter
def dict_key(mapping, key):
    """Safe dictionary lookup for template badge classes."""
    try:
        return mapping.get(key, 'secondary')
    except AttributeError:
        return 'secondary'
