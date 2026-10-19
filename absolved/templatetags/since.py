from typing import TYPE_CHECKING

from django import template
from django.utils.formats import date_format
from django.utils.html import format_html

if TYPE_CHECKING:
    import datetime

    from django.utils.safestring import SafeString

register = template.Library()


@register.simple_tag
def since(date: datetime.date, unit: str) -> SafeString:
    """The time since a date, in `unit`: "natural" (days, weeks, months or years, whichever reads best)
    or "days".

    The page carries the date itself; app.js replaces it with the time from that date to the device's
    today, so a copy of the page kept for offline use stays right.
    """
    return format_html(
        '<time datetime="{}" data-since="{}">{}</time>', date.isoformat(), unit, date_format(date, "j E Y")
    )
