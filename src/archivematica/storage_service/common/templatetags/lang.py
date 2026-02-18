from django import template

register = template.Library()


@register.filter
def standardize_lang_code(language_code):
    """Convert Django language code format (pt-br) into POSIX format (pt_BR)."""
    head, sep, tail = language_code.partition("-")
    if sep == "":
        return head
    return f"{head}_{tail.upper()}"
