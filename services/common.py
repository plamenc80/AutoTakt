"""Общи помощни неща за бизнес логиката."""
import calendar
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

PAGE_SIZE = 10


class BusinessRuleError(Exception):
    """
    Нарушено бизнес правило - съобщението се показва на потребителя.
    field - полето от формата, за което се отнася (напр. „Phone“), за да се покаже до него.
    """

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


@dataclass
class PagedResult:
    items: list
    page: int
    page_size: int
    total_count: int
    search: str | None = None

    @property
    def total_pages(self):
        return math.ceil(self.total_count / self.page_size) if self.page_size else 0

    @property
    def has_previous(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.total_pages

    @property
    def first_index(self):
        return 0 if self.total_count == 0 else (self.page - 1) * self.page_size + 1

    @property
    def last_index(self):
        return min(self.page * self.page_size, self.total_count)

    @property
    def nearby_pages(self):
        return range(max(1, self.page - 2), min(self.total_pages, self.page + 2) + 1)


def paginate(queryset, page, search=None, page_size=PAGE_SIZE):
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1  # „?page=abc“ - първа страница, не грешка
    total = queryset.count()
    page = min(page, max(1, math.ceil(total / page_size)))  # след последната страница - последната
    items = list(queryset[(page - 1) * page_size: page * page_size])
    return PagedResult(items=items, page=page, page_size=page_size, total_count=total, search=search)


def today():
    return date.today()


def start_of_day(day):
    return datetime.combine(day, time())


def add_months(day, months):
    """Добавя месеци, без да прескача края на месеца: 31.01 + 1 месец = 28/29.02."""
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def is_working_day(day):
    return day.weekday() < 5


def phone_key(phone):
    """Телефоните се сравняват само по цифрите; +359 888 … и 0888 … са един номер."""
    digits = re.sub(r"\D", "", phone or "")
    return "0" + digits[3:] if digits.startswith("359") else digits


def clean(text):
    """Празен текст → None, иначе без интервали в краищата."""
    return text.strip() if text and text.strip() else None

