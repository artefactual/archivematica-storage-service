from django import template
from django.urls import reverse


register = template.Library()


@register.simple_tag(takes_context=True)
def logout_link(context):
    if context.get("logout_link"):
        return context["logout_link"]
    else:
        return reverse("logout")
