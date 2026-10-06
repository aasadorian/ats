from decimal import Decimal

from django import template

from apps.lines.models import format_line

register = template.Library()


@register.filter
def line(value: Decimal | None) -> str:
    return format_line(value)
