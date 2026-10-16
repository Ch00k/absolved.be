"""Lucide icons inline in a template, read from the vendored copies so they stay exactly Lucide's."""

from __future__ import annotations

import functools
import re
from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

LUCIDE = "vendor/lucide-1.57.0"


@functools.cache
def lucide_svg(name: str) -> str:
    """The icon's file without its licence comment, its size or its own classes."""
    path = finders.find(f"{LUCIDE}/{name}.svg")
    if not isinstance(path, str):
        msg = f"No Lucide icon {name!r} in static/{LUCIDE}"
        raise template.TemplateSyntaxError(msg)

    svg = re.sub(r"<!--.*?-->\s*", "", Path(path).read_text(), flags=re.DOTALL)
    # Only the opening tag's: the shapes inside, such as a rectangle, have a width and height of their own.
    opening_end = svg.index(">") + 1
    return re.sub(r'\s+(class|width|height)="[^"]*"', "", svg[:opening_end]) + svg[opening_end:]


@register.simple_tag
def icon(name: str, classes: str = "") -> SafeString:
    """The icon, sized and coloured by `classes`, hidden from screen readers like any decoration."""
    opening = format_html('<svg class="{}" aria-hidden="true"', classes)
    return mark_safe(lucide_svg(name).replace("<svg", opening, 1))  # noqa: S308
