from __future__ import absolute_import
from django import template
from django.core.urlresolvers import reverse


register = template.Library()


@register.simple_tag(takes_context=True)
def logout_link(context):
    if context.get("logout_link"):
        return context["logout_link"]
    else:
        return reverse("logout")
