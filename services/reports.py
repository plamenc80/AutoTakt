"""
Справки и табло. Приходите се отчитат по датата на плащане (касов принцип),
а извършената работа - по датата на отваряне на ремонта.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from data.models import (Appointment, AppointmentStatus, Customer, Part, Payment, PaymentMethod, RepairOrder,
                         RepairOrderPartLine, RepairOrderServiceLine, RepairStatus, Vehicle)

from .common import add_months, start_of_day

ZERO = Decimal(0)


@dataclass
class MonthlyRevenue:
    year: int
    month: int
    amount: Decimal
    repairs_count: int

    @property
    def label(self):
        return f"{self.month:02d}.{self.year}"


@dataclass
class PaymentMethodTotal:
    method: str
    amount: Decimal
    count: int

    @property
    def method_name(self):
        return PaymentMethod(self.method).label


@dataclass
class ServiceUsage:
    service_name: str
    times_performed: int
    revenue: Decimal


@dataclass
class PartUsage:
    part_name: str
    part_number: str
    quantity_used: Decimal
    revenue: Decimal
    in_stock: Decimal
    min_stock: int
    unit: str


@dataclass
class MechanicWorkload:
    mechanic_name: str
    repairs_count: int
    labor_revenue: Decimal
    average_hours: float


@dataclass
class PeriodReport:
    start: date
    end: date
    total_revenue: Decimal
    total_labor: Decimal
    total_parts: Decimal
    repairs_count: int
    revenue_by_month: list = field(default_factory=list)
    by_payment_method: list = field(default_factory=list)
    top_services: list = field(default_factory=list)
    parts_usage: list = field(default_factory=list)
    mechanics: list = field(default_factory=list)

    @property
    def average_repair_value(self):
        if self.repairs_count == 0:
            return ZERO
        return ((self.total_labor + self.total_parts) / self.repairs_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _sum(queryset, column):
    return queryset.aggregate(total=Sum(column))["total"] or ZERO


def _payments_between(start, end):
    return Payment.objects.filter(paid_on__gte=start_of_day(start), paid_on__lt=start_of_day(end))


def revenue_by_month(start, end):
    """Приходи по месеци; месеците без плащания също се показват (с 0)."""
    totals, orders = defaultdict(lambda: ZERO), defaultdict(set)
    for paid_on, amount, order_id in _payments_between(start, end).values_list("paid_on", "amount", "repair_order_id"):
        totals[(paid_on.year, paid_on.month)] += amount
        orders[(paid_on.year, paid_on.month)].add(order_id)
    result, month = [], date(start.year, start.month, 1)
    while month < end:
        key = (month.year, month.month)
        result.append(MonthlyRevenue(month.year, month.month, totals[key], len(orders[key])))
        month = add_months(month, 1)
    return result


def dashboard():
    today = date.today()
    month_start = today.replace(day=1)
    open_statuses = [RepairStatus.OPEN, RepairStatus.IN_PROGRESS]
    unpaid = sum((o.remaining_amount for o in RepairOrder.objects.filter(status=RepairStatus.DONE).prefetch_related("payments")), ZERO)
    active_appointments = Appointment.objects.exclude(status=AppointmentStatus.CANCELLED)
    return {
        "today_appointments": active_appointments.filter(scheduled_for__date=today).count(),
        "pending_appointments": Appointment.objects.filter(status=AppointmentStatus.PENDING).count(),
        "open_repairs": RepairOrder.objects.filter(status__in=open_statuses).count(),
        "revenue_this_month": _sum(_payments_between(month_start, add_months(month_start, 1)), "amount"),
        "revenue_last_month": _sum(_payments_between(add_months(month_start, -1), month_start), "amount"),
        "unpaid_amount": unpaid,
        "customers_count": Customer.objects.count(),
        "vehicles_count": Vehicle.objects.count(),
        "low_stock_parts": [p for p in Part.objects.order_by("quantity_in_stock") if p.is_low_stock],
        "upcoming_appointments": list(active_appointments.exclude(status=AppointmentStatus.COMPLETED)
                                      .filter(scheduled_for__gte=start_of_day(today))
                                      .select_related("customer", "vehicle").order_by("scheduled_for")[:6]),
        "active_repairs": list(RepairOrder.objects.filter(status__in=open_statuses)
                               .select_related("vehicle", "customer", "mechanic").order_by("opened_on")[:6]),
        "revenue_by_month": revenue_by_month(add_months(month_start, -11), add_months(month_start, 1)),
    }


def period_report(start, end):
    """Пълна справка за периода (включително последния ден)."""
    stop = end + timedelta(days=1)
    repairs = RepairOrder.objects.filter(opened_on__gte=start_of_day(start), opened_on__lt=start_of_day(stop))
    finished = repairs.filter(status__in=[RepairStatus.DONE, RepairStatus.PAID])

    by_method = defaultdict(lambda: [ZERO, 0])
    for method, amount in _payments_between(start, stop).values_list("method", "amount"):
        by_method[method][0] += amount
        by_method[method][1] += 1
    methods = sorted((PaymentMethodTotal(m, a, c) for m, (a, c) in by_method.items()), key=lambda m: -m.amount)

    services = defaultdict(lambda: [0, ZERO])
    # Услугите и частите - само от завършените ремонти, като „Труд“ и „Части“ (незапочнатата работа не е извършена).
    for name, quantity, price in RepairOrderServiceLine.objects.filter(repair_order__in=finished) \
            .values_list("service__name", "quantity", "price_at_time"):
        services[name][0] += quantity
        services[name][1] += quantity * price
    top_services = sorted((ServiceUsage(n, c, r) for n, (c, r) in services.items()), key=lambda s: -s.times_performed)[:10]

    parts = {}
    for line in RepairOrderPartLine.objects.filter(repair_order__in=finished).select_related("part"):
        p = line.part
        usage = parts.setdefault(p.id, PartUsage(p.name, p.part_number, ZERO, ZERO, p.quantity_in_stock, p.min_stock_level, p.unit))
        usage.quantity_used += line.quantity
        usage.revenue += line.quantity * line.unit_price_at_time
    parts_usage = sorted(parts.values(), key=lambda p: -p.quantity_used)

    mechanic_rows = defaultdict(list)
    for name, labor, opened, closed in finished.filter(mechanic__isnull=False, closed_on__isnull=False) \
            .values_list("mechanic__full_name", "total_labor", "opened_on", "closed_on"):
        mechanic_rows[name].append((labor, (closed - opened).total_seconds() / 3600))
    mechanics = sorted((MechanicWorkload(n, len(rows), sum((r[0] for r in rows), ZERO),
                                         round(sum(r[1] for r in rows) / len(rows), 1))
                        for n, rows in mechanic_rows.items()), key=lambda m: -m.repairs_count)

    return PeriodReport(
        start=start, end=end, total_revenue=sum((m.amount for m in methods), ZERO),
        total_labor=_sum(finished, "total_labor"), total_parts=_sum(finished, "total_parts"),
        repairs_count=finished.count(), revenue_by_month=revenue_by_month(start, stop),
        by_payment_method=methods, top_services=top_services, parts_usage=parts_usage, mechanics=mechanics)
