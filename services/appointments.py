"""Записване на часове."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count

from data.models import (Appointment, AppointmentStatus, Customer, FuelType, PartsPreference, Service, Transmission,
                         Vehicle)

from . import customers
from .common import BusinessRuleError, clean, is_working_day, phone_key, start_of_day
from .customers import REVIEW_NOTE
from .plates import check_vin, normalize_plate

FIRST_HOUR = 8       # работно време за записване
LAST_HOUR = 17
SLOT_CAPACITY = 3    # работни места (подемници) - толкова коли за един и същ час
MAX_GUEST_BOOKINGS_PER_DAY = 2
REPEAT_WINDOW = timedelta(minutes=2)  # същото записване, изпратено повторно (двоен клик, бавна връзка)

_RELATED = ("customer", "vehicle", "service")


def for_period(start, end):
    return list(Appointment.objects.select_related(*_RELATED)
                .filter(scheduled_for__gte=start, scheduled_for__lt=end).order_by("scheduled_for"))


def for_customer(customer_id):
    return list(Appointment.objects.select_related("vehicle", "service")
                .filter(customer_id=customer_id).order_by("-scheduled_for"))


def get(appointment_id):
    return Appointment.objects.select_related(*_RELATED).filter(id=appointment_id).first()


def free_slots(day):
    """Свободните часове за деня (минали и пълни - не)."""
    if not is_working_day(day):
        return []
    start = start_of_day(day)
    taken = {}
    for appointment in Appointment.objects.filter(scheduled_for__gte=start, scheduled_for__lt=start + timedelta(days=1)) \
            .exclude(status=AppointmentStatus.CANCELLED):
        taken[appointment.scheduled_for.hour] = taken.get(appointment.scheduled_for.hour, 0) + 1
    now = datetime.now()
    return [start + timedelta(hours=h) for h in range(FIRST_HOUR, LAST_HOUR + 1)
            if start + timedelta(hours=h) > now and taken.get(h, 0) < SLOT_CAPACITY]


def book(appointment, allow_foreign_vehicle=False):
    """
    Записва час. Правила: не в миналото; работни дни на кръгъл час 8-17; до 3 коли за час;
    един час на ден за кола; колата трябва да е на клиента (освен при гост - тогава „За проверка“).
    Проверките и записът са в една транзакция (SQLite: IMMEDIATE) - двама едновременно не могат да вземат
    последното място. Повторно изпратена форма (двоен клик) връща вече записания час вместо грешка.
    """
    when = appointment.scheduled_for
    if when <= datetime.now():
        raise BusinessRuleError("Не може да се запише час в миналото.")
    if not is_working_day(when) or not FIRST_HOUR <= when.hour <= LAST_HOUR or when.minute or when.second:
        raise BusinessRuleError(f"Часовете са през работните дни, на кръгъл час, от {FIRST_HOUR}:00 до {LAST_HOUR}:00.")
    with transaction.atomic():
        vehicle = Vehicle.objects.filter(id=appointment.vehicle_id).first()
        if vehicle is None:
            raise BusinessRuleError("Автомобилът не е намерен.")
        if vehicle.customer_id != appointment.customer_id and not allow_foreign_vehicle:
            raise BusinessRuleError("Автомобилът не принадлежи на избрания клиент.")
        active = Appointment.objects.exclude(status=AppointmentStatus.CANCELLED)
        repeat = active.filter(vehicle_id=appointment.vehicle_id, customer_id=appointment.customer_id, scheduled_for=when,
                               created_on__gte=datetime.now() - REPEAT_WINDOW).first()
        if repeat:
            return repeat.id
        if active.filter(scheduled_for=when).count() >= SLOT_CAPACITY:
            raise BusinessRuleError("Този час вече е зает. Моля, изберете друг.")
        day = start_of_day(when.date())
        if active.filter(vehicle_id=appointment.vehicle_id, scheduled_for__gte=day, scheduled_for__lt=day + timedelta(days=1)).exists():
            raise BusinessRuleError("Този автомобил вече има записан час за същия ден.")
        if appointment.service_id and not Service.objects.filter(id=appointment.service_id, is_active=True).exists():
            raise BusinessRuleError("Избраната услуга не е налична.")
        appointment.status = AppointmentStatus.PENDING
        appointment.created_on = datetime.now()
        appointment.save()
    return appointment.id


def change_status(appointment_id, status):
    appointment = Appointment.objects.filter(id=appointment_id).first()
    if appointment is None:
        raise BusinessRuleError("Записаният час не е намерен.")
    if appointment.status in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
        raise BusinessRuleError("Часът вече е приключен или отказан и не може да се променя.")
    appointment.status = status
    if status in (AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED):
        appointment.needs_review = False  # вече е проверен от рецепцията
    appointment.save()


# ---------------------------------------------------------------------------- записване от гост
@dataclass
class GuestBookingRequest:
    full_name: str
    phone: str
    email: str | None
    license_plate: str
    make: str
    model: str
    year: int
    service_id: int | None
    scheduled_for: datetime
    description: str
    fuel_type: str = FuelType.UNKNOWN
    transmission: str = Transmission.UNKNOWN
    vin: str | None = None
    mileage: int | None = None
    parts_preference: str = PartsPreference.MECHANIC_DECIDES
    parts_note: str | None = None


@dataclass
class GuestBookingResult:
    appointment_id: int
    existing_customer: bool
    needs_review: bool
    customer_id: int = 0
    # Профил, създаден веднага след записването (от същия човек), може да поеме клиента - вж. customers.link_account.
    claimable: bool = False
    # Часът е към клиент с онлайн профил - вижда го, като влезе.
    has_profile: bool = False
    # Номерът е на друг клиент - автомобилът не е на госта, рецепцията го проверява.
    foreign_vehicle: bool = False


PHONE_NOTE = "Телефонът е и на {names} от картотеката - проверете дали е същият човек."


def book_guest(request):
    """
    Записване без профил. Телефон и рег. номер на автомобил на съществуващ клиент → часът е към него.
    Иначе → нов клиент (гост): само по телефон не се добавят автомобил или час към чужд клиент (и към профил);
    номер на чужд автомобил или телефон на друг клиент → „За проверка“ (без да се показват чужди данни).
    До 2 записвания на телефон на ден. Часът винаги е „Чакащ“ - рецепцията го потвърждава.
    """
    key = phone_key(request.phone)
    if len(key) < 6:
        raise BusinessRuleError("Въведете валиден телефонен номер.", field="Phone")
    email = clean(request.email)
    plate = normalize_plate(request.license_plate)
    with transaction.atomic():
        same_phone = [c for c in Customer.objects.only("id", "full_name", "phone", "email", "user_id", "created_on")
                      if phone_key(c.phone) == key]
        vehicle = Vehicle.objects.filter(license_plate=plate).first()
        owner = next((c for c in same_phone if vehicle and c.id == vehicle.customer_id), None)

        repeat = _repeated_guest_booking(vehicle, request.scheduled_for, key)
        if repeat:
            return _result(repeat, request.phone, email, fresh=repeat.customer.created_on >= datetime.now() - REPEAT_WINDOW)

        if Appointment.objects.filter(customer_id__in=[c.id for c in same_phone], is_guest_booking=True,
                                      created_on__gte=start_of_day(datetime.now().date())).count() >= MAX_GUEST_BOOKINGS_PER_DAY:
            raise BusinessRuleError("Днес вече сте записали час от този телефон. За промени се обадете в сервиза.", field="Phone")

        notes = []
        if owner is not None:
            customer = owner
        else:
            customer = Customer.objects.create(full_name=request.full_name.strip(), phone=request.phone.strip(),
                                               email=email, created_on=datetime.now())
            if vehicle is None:
                # VIN се записва само ако е валиден и не е на друг автомобил (иначе - при приемане).
                vin = request.vin.strip().upper() if request.vin and request.vin.strip() else None
                if vin and (not check_vin(vin).is_valid_format or Vehicle.objects.filter(vin=vin).exists()):
                    vin = None
                vehicle = Vehicle.objects.create(customer=customer, license_plate=plate, make=request.make.strip(),
                                                 model=request.model.strip(), year=request.year, fuel_type=request.fuel_type,
                                                 transmission=request.transmission, vin=vin, mileage=max(0, request.mileage or 0))
            else:
                notes.append(REVIEW_NOTE)
            if same_phone:
                notes.append(PHONE_NOTE.format(names=", ".join(c.full_name for c in same_phone[:3])))
        foreign = vehicle.customer_id != customer.id
        appointment_id = book(Appointment(
            customer=customer, vehicle=vehicle, service_id=request.service_id, scheduled_for=request.scheduled_for,
            description=request.description.strip(), is_guest_booking=True, parts_preference=request.parts_preference,
            parts_note=clean(request.parts_note), needs_review=bool(notes),
            review_note=" ".join(notes)[:300] or None), allow_foreign_vehicle=foreign)
        appointment = Appointment.objects.select_related("customer").get(id=appointment_id)
        result = _result(appointment, request.phone, email, fresh=owner is None)
        if owner is not None and result.claimable and email and not owner.email:
            # Доказан с телефон и номер - имейлът се допълва, за да се свърже и при регистрация от друго устройство.
            owner.email = email
            owner.save(update_fields=["email"])
    return result


def _repeated_guest_booking(vehicle, when, key):
    """Същото записване (автомобил, час и телефон) отпреди секунди - повторно изпратена форма."""
    if vehicle is None:
        return None
    recent = (Appointment.objects.select_related("customer")
              .filter(vehicle=vehicle, scheduled_for=when, is_guest_booking=True,
                      created_on__gte=datetime.now() - REPEAT_WINDOW)
              .exclude(status=AppointmentStatus.CANCELLED).first())
    return recent if recent and phone_key(recent.customer.phone) == key else None


def _result(appointment, phone, email, fresh):
    """fresh - клиентът е създаден от това записване (гостът е този човек)."""
    customer = appointment.customer
    owns_plate = appointment.vehicle.customer_id == customer.id
    claimable = customer.user_id is None and (fresh or customers.proves_identity(customer, phone, email, owns_plate))
    return GuestBookingResult(appointment.id, not fresh, appointment.needs_review, customer.id, claimable,
                              customer.user_id is not None, not owns_plate)
