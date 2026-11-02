"""Таблото на механика и рецепция „Днес“."""
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Prefetch, Q

from data.models import Appointment, AppointmentStatus, RepairOrder, RepairOrderServiceLine, RepairStatus, Vehicle

from .common import start_of_day
from .plates import normalize_plate

ACTIVE_APPOINTMENT = (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED)


def _today_range():
    start = start_of_day(date.today())
    return start, start + timedelta(days=1)


@dataclass
class WorkshopBoard:
    arriving: list   # записани за днес, още не приети
    accepted: list
    in_progress: list
    ready: list      # завършени, чакат клиента


def board(mechanic_id=None):
    """Четирите колони. С mechanic_id - само ремонтите на механика и невъзложените."""
    start, end = _today_range()
    arriving = list(Appointment.objects.select_related("customer", "vehicle", "service")
                    .filter(scheduled_for__gte=start, scheduled_for__lt=end, status__in=ACTIVE_APPOINTMENT)
                    .order_by("scheduled_for"))
    query = (RepairOrder.objects.select_related("vehicle", "customer", "mechanic")
             .prefetch_related(Prefetch("service_lines", RepairOrderServiceLine.objects.select_related("service").order_by("id")),
                               "recommendations")
             .exclude(status=RepairStatus.PAID))
    if mechanic_id:
        query = query.filter(Q(mechanic_id=mechanic_id) | Q(mechanic__isnull=True))
    orders = list(query.order_by("opened_on"))
    return WorkshopBoard(arriving,
                         [o for o in orders if o.status == RepairStatus.OPEN],
                         [o for o in orders if o.status == RepairStatus.IN_PROGRESS],
                         [o for o in orders if o.status == RepairStatus.DONE])


@dataclass
class PlateMatch:
    vehicle: Vehicle
    active_repair: RepairOrder | None
    next_appointment: Appointment | None
    visits_count: int


def lookup(plate):
    """Търсене по част от номера („1234“, „сн1234“, „CH 1234 AB“ на латиница) - точното съвпадение е първо."""
    compact = normalize_plate(plate or "").replace(" ", "")
    if len(compact) < 2:
        return []
    vehicles = [v for v in Vehicle.objects.select_related("customer") if compact in v.license_plate.replace(" ", "")][:5]
    ids = [v.id for v in vehicles]
    active = list(RepairOrder.objects.filter(vehicle_id__in=ids).exclude(status=RepairStatus.PAID))
    upcoming = list(Appointment.objects.filter(vehicle_id__in=ids, scheduled_for__gte=start_of_day(date.today()),
                                               status__in=ACTIVE_APPOINTMENT).order_by("scheduled_for"))
    visits = dict(RepairOrder.objects.filter(vehicle_id__in=ids).values("vehicle_id").annotate(n=Count("id")).values_list("vehicle_id", "n"))
    matches = []
    for v in sorted(vehicles, key=lambda v: v.license_plate.replace(" ", "") != compact):
        mine = [r for r in active if r.vehicle_id == v.id]
        matches.append(PlateMatch(v, max(mine, key=lambda r: r.opened_on) if mine else None,
                                  next((a for a in upcoming if a.vehicle_id == v.id), None), visits.get(v.id, 0)))
    return matches


def today_overview():
    """Всичко за рецепцията днес: пристигащи, за проверка, в сервиза, чакат плащане."""
    start, end = _today_range()
    related = ("customer", "vehicle", "service")
    return {
        "arrivals": list(Appointment.objects.select_related(*related)
                         .filter(scheduled_for__gte=start, scheduled_for__lt=end).order_by("scheduled_for")),
        "needs_review": list(Appointment.objects.select_related(*related)
                             .filter(needs_review=True, status=AppointmentStatus.PENDING, scheduled_for__gte=start)
                             .order_by("scheduled_for")),
        "in_workshop": list(RepairOrder.objects.select_related("vehicle", "customer", "mechanic")
                            .filter(status__in=[RepairStatus.OPEN, RepairStatus.IN_PROGRESS]).order_by("opened_on")),
        "awaiting_payment": list(RepairOrder.objects.select_related("vehicle", "customer").prefetch_related("payments")
                                 .filter(status=RepairStatus.DONE).order_by("closed_on")),
    }
