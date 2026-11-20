"""Малки филтри за страниците на ремонтите, таблото и проверката."""
from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def invariant(value):
    """Число с точка, без излишни нули - за data-атрибути и стойности в полета (4.30 → „4.3“)."""
    if value is None or value == "":
        return ""
    number = Decimal(str(value))
    text = f"{number:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


@register.filter
def money_input(value):
    """Сума за <input type="number">: „123.40“ (винаги с точка и 2 знака)."""
    return f"{Decimal(str(value or 0)):.2f}"


@register.filter
def rec_tone(status):
    """Тон на чипа на препоръка: одобрена - ok, отказана - neutral, предложена - warn."""
    return {"Approved": "ok", "Declined": "neutral"}.get(status, "warn")


@register.filter
def first_word(text):
    return (text or "").split(" ")[0]


@register.filter
def rated_count(inspection):
    """Колко точки от проверката вече са оценени."""
    return sum(1 for r in inspection.results.all() if r.rating != "Unrated")


@register.filter
def in_shop(opened_on):
    """„3 ч в сервиза“, „2 дни в сервиза“."""
    from datetime import datetime
    hours = (datetime.now() - opened_on).total_seconds() / 3600
    if hours < 1:
        return "по-малко от час"
    if hours < 24:
        return f"{int(hours)} ч в сервиза"
    days = int(hours // 24)
    return f"{days} {'ден' if days == 1 else 'дни'} в сервиза"


@register.filter
def ready_since(closed_on):
    """„готов от 14:30“ (днес) или „готов от 07.10“."""
    from datetime import date
    if closed_on is None:
        return "готов от "
    return "готов от " + (closed_on.strftime("%H:%M") if closed_on.date() == date.today() else closed_on.strftime("%d.%m"))


@register.filter
def waiting_count(order):
    """Колко препоръки чакат решение на клиента."""
    return sum(1 for r in order.recommendations.all() if r.status == "Proposed")


@register.filter
def done_percent(order):
    lines = list(order.service_lines.all())
    return sum(1 for line in lines if line.is_done) * 100 // len(lines) if lines else 0


@register.filter
def services_summary(order):
    return ", ".join(line.service.name for line in order.service_lines.all())
