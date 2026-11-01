"""Автомобили и „здравето“ им."""
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Prefetch, Q

from data.models import FuelType, RepairOrder, RepairStatus, Service, ServicePackageItem, Transmission, Vehicle

from .common import BusinessRuleError, add_months, clean, paginate
from .plates import check_vin, normalize_plate

VIN_ERROR = "VIN трябва да съдържа точно 17 символа (латински букви без I, O, Q и цифри)."


def search(term, page):
    query = Vehicle.objects.select_related("customer")
    if term and term.strip():
        t = term.strip()
        query = query.filter(Q(license_plate__icontains=normalize_plate(t)) | Q(vin__icontains=t.upper())
                             | Q(make__icontains=t) | Q(model__icontains=t) | Q(customer__full_name__icontains=t))
    return paginate(query.order_by("make", "model"), page, search=term)


def get(vehicle_id):
    return Vehicle.objects.select_related("customer", "engine_variant").filter(id=vehicle_id).first()


def for_customer(customer_id):
    return list(Vehicle.objects.filter(customer_id=customer_id).order_by("make"))


def get_history(vehicle_id):
    """Автомобилът с всички ремонти (услуги, части, механик, плащания) - за историята."""
    orders = (RepairOrder.objects.select_related("mechanic")
              .prefetch_related("service_lines__service", "part_lines__part", "payments")
              .order_by("-opened_on"))
    return (Vehicle.objects.select_related("customer", "engine_variant")
            .prefetch_related("engine_variant__fluids", Prefetch("repair_orders", orders))
            .filter(id=vehicle_id).first())


def _normalize(vehicle):
    """VIN и рег. номер се пазят в единен формат (главни букви, кирилица за номера)."""
    vehicle.vin = vehicle.vin.strip().upper() if vehicle.vin and vehicle.vin.strip() else None
    vehicle.license_plate = normalize_plate(vehicle.license_plate)


def _ensure_unique(vehicle):
    others = Vehicle.objects.exclude(id=vehicle.id) if vehicle.id else Vehicle.objects.all()
    if vehicle.vin and others.filter(vin=vehicle.vin).exists():
        raise BusinessRuleError(f"Вече има автомобил с VIN {vehicle.vin}.")
    if others.filter(license_plate=vehicle.license_plate).exists():
        raise BusinessRuleError(f"Вече има автомобил с рег. номер {vehicle.license_plate}.")


@transaction.atomic
def save(vehicle, previous_owner=None, transfer_history=False):
    """
    Създава или обновява автомобил (номерът и VIN се нормализират и трябва да са уникални).
    При смяна на собственика досегашните ремонти остават на предишния (продадена кола - протоколите са негови);
    transfer_history - собственикът е бил записан грешно и историята минава към новия.
    """
    _normalize(vehicle)
    _ensure_unique(vehicle)
    vehicle.save()
    if transfer_history and previous_owner and previous_owner != vehicle.customer_id:
        RepairOrder.objects.filter(vehicle=vehicle, customer_id=previous_owner).update(customer_id=vehicle.customer_id)
    return vehicle


def complete_registration(vehicle_id, vin=None, first_registration=None, engine_cc=None, power_kw=None,
                          variant=None, color=None, transmission=None, fuel_type=None):
    """Данни от талона, попълнени при приемане - празните полета не изтриват записаното."""
    vehicle = Vehicle.objects.filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")
    if vin and vin.strip():
        if not check_vin(vin).is_valid_format:
            raise BusinessRuleError(VIN_ERROR)
        vehicle.vin = vin.strip().upper()
        _ensure_unique(vehicle)
    vehicle.first_registration = first_registration or vehicle.first_registration
    vehicle.engine_cc = engine_cc or vehicle.engine_cc
    vehicle.power_kw = power_kw or vehicle.power_kw
    vehicle.variant = clean(variant) or vehicle.variant
    vehicle.color = clean(color) or vehicle.color
    if transmission and transmission != Transmission.UNKNOWN:
        vehicle.transmission = transmission
    if fuel_type and fuel_type != FuelType.UNKNOWN:
        vehicle.fuel_type = fuel_type
    vehicle.save()


def find_by_plate(plate):
    return Vehicle.objects.filter(license_plate=normalize_plate(plate)).first() if plate and plate.strip() else None


def delete(vehicle_id):
    vehicle = Vehicle.objects.filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")
    if vehicle.repair_orders.exists():
        raise BusinessRuleError("Автомобилът има история на ремонти и не може да бъде изтрит.")
    vehicle.delete()


# ---------------------------------------------------------------------------- здраве
SOON_KM = 1500   # под толкова километри или дни до обслужването - „Наближава“
SOON_DAYS = 30

OK, SOON, OVERDUE, UNKNOWN = "Ok", "Soon", "Overdue", "Unknown"


@dataclass
class HealthItem:
    service_id: int
    service_name: str
    interval_km: int | None
    interval_months: int | None
    last_date: date | None
    last_mileage: int | None
    due_mileage: int | None
    due_date: date | None
    remaining_km: int | None
    remaining_days: int | None
    progress: float
    status: str


def evaluate(service, last_date, last_mileage, current_mileage, today):
    """
    Състоянието на едно периодично обслужване. Следващото е при каквото настъпи първо - км или време.
    Прогресът е колко от интервала е „изразходван“ (0 = току-що направено, 1 = време е).
    """
    if last_date is None:
        return HealthItem(service.id, service.name, service.interval_km, service.interval_months,
                          None, None, None, None, None, None, 0, UNKNOWN)
    last_day = last_date.date() if hasattr(last_date, "date") else last_date
    due_mileage = last_mileage + service.interval_km if (service.interval_km or 0) > 0 and last_mileage is not None else None
    due_date = add_months(last_day, service.interval_months) if (service.interval_months or 0) > 0 else None
    remaining_km = due_mileage - current_mileage if due_mileage is not None else None
    remaining_days = (due_date - today).days if due_date else None
    km_progress = (current_mileage - last_mileage) / service.interval_km if due_mileage is not None else 0
    time_progress = (today - last_day).days / (due_date - last_day).days if due_date else 0
    progress = max(0, km_progress, time_progress)

    def at_most(value, limit):
        return value is not None and value <= limit

    status = (OVERDUE if at_most(remaining_km, 0) or at_most(remaining_days, 0)
              else SOON if at_most(remaining_km, SOON_KM) or at_most(remaining_days, SOON_DAYS)
              else OK)
    return HealthItem(service.id, service.name, service.interval_km, service.interval_months, last_day, last_mileage,
                      due_mileage, due_date, remaining_km, remaining_days, round(progress, 3), status)


def health_for_vehicles(vehicle_ids):
    """„Здраве“ за няколко автомобила наведнъж: {id: [HealthItem, ...]} - първо просрочените."""
    services = list(Service.objects.filter(is_active=True).filter(Q(interval_km__gt=0) | Q(interval_months__gt=0)))
    mileage = dict(Vehicle.objects.filter(id__in=vehicle_ids).values_list("id", "mileage"))

    # Кога за последно е извършена всяка услуга (само завършени ремонти).
    from data.models import RepairOrderServiceLine
    rows = (RepairOrderServiceLine.objects
            .filter(repair_order__vehicle_id__in=vehicle_ids, repair_order__status__in=[RepairStatus.DONE, RepairStatus.PAID])
            .values_list("repair_order__vehicle_id", "service_id", "repair_order__opened_on",
                         "repair_order__mileage_at_service", "package_items"))
    # Пакет (напр. „Голямо обслужване“) се брои като извършване на всяка включена услуга - по състава му
    # към момента на ремонта (за стари редове без запомнен състав - по сегашния).
    current_items = {}
    for package_id, service_id in ServicePackageItem.objects.values_list("package_id", "service_id"):
        current_items.setdefault(package_id, []).append(service_id)
    history = []
    for v, sid, opened, km, items in rows:
        history.append((v, sid, opened, km))
        included = [item[0] for item in items] if items else current_items.get(sid, [])
        history += [(v, service_id, opened, km) for service_id in included]

    order = {OVERDUE: 0, SOON: 1, OK: 2, UNKNOWN: 3}
    today = date.today()
    result = {}
    for vehicle_id, current in mileage.items():
        items = []
        for service in services:
            done = [h for h in history if h[0] == vehicle_id and h[1] == service.id]
            last = max(done, key=lambda h: h[2]) if done else None
            items.append(evaluate(service, last[2] if last else None, last[3] if last else None, current, today))
        result[vehicle_id] = sorted(items, key=lambda i: (order[i.status], -i.progress))
    return result


def health(vehicle_id):
    return health_for_vehicles([vehicle_id]).get(vehicle_id, [])
