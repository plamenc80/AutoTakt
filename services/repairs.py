"""Ремонти: услуги, части, статуси, плащания и препоръки."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Max, Prefetch, Q

from data.models import (Appointment, AppointmentStatus, Inspection, InspectionRating, InspectionResult, Mechanic, Part,
                         PartChoice, PartUnit, Payment, Recommendation, RecommendationStatus, RepairOrder,
                         RepairOrderPartLine, RepairOrderServiceLine, RepairStatus, Service, ServicePackageItem, Vehicle,
                         FitStatus, round_money)

from .common import BusinessRuleError, clean, paginate, start_of_day

MAX_SERVICE_QUANTITY = 1000
MAX_PART_QUANTITY = Decimal(100_000)
MAX_MILEAGE = 3_000_000
from .engines import evaluate_fit, vehicle_for_fit
from .plates import normalize_plate

OPEN_STATUSES = (RepairStatus.OPEN, RepairStatus.IN_PROGRESS)
ACTIVE_APPOINTMENT = (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED)


def search(term, status, mechanic_id, page):
    query = RepairOrder.objects.select_related("vehicle", "customer", "mechanic")
    if isinstance(status, (list, tuple)):  # няколко статуса - напр. текущите (отворени и в процес)
        query = query.filter(status__in=status)
    elif status:
        query = query.filter(status=status)
    if mechanic_id:
        query = query.filter(mechanic_id=mechanic_id)
    if term and term.strip():
        t = term.strip()
        condition = Q(vehicle__license_plate__icontains=normalize_plate(t)) | Q(customer__full_name__icontains=t)
        if t.isascii() and t.isdigit():
            condition |= Q(id=int(t))
        query = query.filter(condition)
    return paginate(query.order_by("-opened_on"), page, search=term)


def _with_package_items():
    return Prefetch("service_lines", RepairOrderServiceLine.objects.select_related("service")
                    .prefetch_related(Prefetch("service__package_items", ServicePackageItem.objects.select_related("service")))
                    .order_by("id"))


def details(order_id):
    """Ремонтът с всичко за страницата му: кола, клиент, двигател, услуги (и пакети), части, плащания, препоръки."""
    return (RepairOrder.objects
            .select_related("vehicle__customer", "vehicle__engine_variant", "customer", "mechanic")
            .prefetch_related("vehicle__engine_variant__fluids", _with_package_items(),
                              Prefetch("part_lines", RepairOrderPartLine.objects.select_related("part").order_by("id")),
                              "payments", Prefetch("recommendations", Recommendation.objects.select_related("service").order_by("created_on")))
            .filter(id=order_id).first())


def active_for_customer(customer_id):
    """Неплатените ремонти на клиента - за проследяването в „Моят гараж“."""
    results = InspectionResult.objects.select_related("template_item").prefetch_related("photos").order_by("template_item__sort_order")
    return list(RepairOrder.objects
                .select_related("vehicle", "mechanic")
                .prefetch_related(_with_package_items(), "payments",
                                  Prefetch("recommendations", Recommendation.objects.select_related("service")
                                           .prefetch_related("inspection_result__photos").order_by("created_on")),
                                  Prefetch("inspections", Inspection.objects.select_related("template")
                                           .prefetch_related(Prefetch("results", results))))
                .filter(customer_id=customer_id).exclude(status=RepairStatus.PAID)
                .order_by("-opened_on"))


def _editable(order_id):
    """Ремонт, който още може да се редактира (не е завършен или платен)."""
    order = RepairOrder.objects.filter(id=order_id).first()
    if order is None:
        raise BusinessRuleError("Ремонтът не е намерен.")
    if order.status in (RepairStatus.DONE, RepairStatus.PAID):
        raise BusinessRuleError("Ремонтът е приключен и не може да се редактира. Върнете го в статус „В процес“.")
    return order


def _save_totals(order):
    order.recalculate_totals()
    order.save(update_fields=["total_labor", "total_parts", "vat", "total_amount"])


def _add_line(order, service, quantity, price):
    """Ред за услуга: цената и съставът на пакета се запомнят - после промяна в ценоразписа не пипа историята."""
    items = [[i.service_id, i.service.name] for i in service.package_items.select_related("service").order_by("id")] \
        if service.is_package else []
    return RepairOrderServiceLine.objects.create(repair_order=order, service=service, quantity=quantity,
                                                 price_at_time=price, package_items=items)


@transaction.atomic
def create(vehicle_id, mechanic_id, mileage, notes=None, appointment_id=None):
    """
    Нов ремонт. Една кола не може да има два отворени ремонта; пробегът не може да намалява.
    Ако е по записан час - часът трябва да е активен и проверен (не „За проверка“); става „Изпълнен“, а заявената
    услуга се добавя автоматично.
    """
    vehicle = Vehicle.objects.filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")
    appointment = _appointment_for(vehicle, appointment_id)
    open_order = RepairOrder.objects.filter(vehicle_id=vehicle_id, status__in=OPEN_STATUSES).values_list("id", flat=True).first()
    if open_order:
        raise BusinessRuleError(f"Автомобилът вече има отворен ремонт № {open_order:06d}.")
    if mileage < vehicle.mileage:
        raise BusinessRuleError(f"Пробегът не може да е по-малък от последно записания ({vehicle.mileage:,} км).".replace(",", " "))
    vehicle.mileage = mileage
    vehicle.save(update_fields=["mileage"])

    order = RepairOrder.objects.create(vehicle=vehicle, customer_id=vehicle.customer_id, mechanic_id=mechanic_id,
                                       mileage_at_service=mileage, notes=clean(notes),
                                       appointment_id=appointment.id if appointment else None, opened_on=datetime.now(),
                                       status=RepairStatus.OPEN)
    if appointment:
        appointment.status = AppointmentStatus.COMPLETED
        appointment.save(update_fields=["status"])
        order.parts_preference, order.parts_note = appointment.parts_preference, appointment.parts_note
        order.save(update_fields=["parts_preference", "parts_note"])
        if appointment.service_id and (service := Service.objects.filter(id=appointment.service_id).first()):
            _add_line(order, service, 1, service.price)
            _save_totals(order)
    return order.id


def todays_appointment_id(vehicle_id):
    """
    Днешният записан час на колата (активен и проверен) - „Нов ремонт“ за кола, която е записана за днес,
    е същото посещение: часът се свързва, вместо да остане „Потвърден“ в графика.
    """
    today = start_of_day(date.today())
    return (Appointment.objects.filter(vehicle_id=vehicle_id, status__in=ACTIVE_APPOINTMENT, needs_review=False,
                                       scheduled_for__gte=today, scheduled_for__lt=today + timedelta(days=1))
            .order_by("scheduled_for").values_list("id", flat=True).first())


def _appointment_for(vehicle, appointment_id):
    """Записаният час, по който се приема колата - или None. Само активен и проверен час на същата кола."""
    if not appointment_id:
        return None
    appointment = Appointment.objects.filter(id=appointment_id).first()
    if appointment is None:
        raise BusinessRuleError("Записаният час не е намерен.")
    if appointment.vehicle_id != vehicle.id:
        raise BusinessRuleError("Записаният час е за друг автомобил.")
    if appointment.status not in ACTIVE_APPOINTMENT:
        raise BusinessRuleError("Този час вече е приключен или отказан.")
    if appointment.needs_review:
        raise BusinessRuleError("Записването е „За проверка“ (номерът е на друг клиент) - рецепцията първо трябва да го "
                                "потвърди или откаже.")
    return appointment


def update_info(order_id, mechanic_id, mileage, notes):
    """
    Механик, пробег и бележки. Пробегът при приемане е последният известен за колата - записва се и в нея
    (ако това е последният ѝ ремонт) и не може да е по-малък от записания при предишен ремонт.
    """
    if mileage is None or not 0 <= mileage <= MAX_MILEAGE:
        raise BusinessRuleError("Невалиден пробег.")
    order = _editable(order_id)
    previous = RepairOrder.objects.filter(vehicle_id=order.vehicle_id, opened_on__lt=order.opened_on).exclude(id=order.id)
    floor = previous.aggregate(m=Max("mileage_at_service"))["m"] or 0
    if mileage < floor:
        raise BusinessRuleError(f"Пробегът не може да е по-малък от записания при предишен ремонт ({floor:,} км).".replace(",", " "))
    mechanic_id = mechanic_id or None
    # Неактивен механик остава на ремонтите си, но нов не може да се възложи.
    if mechanic_id and mechanic_id != order.mechanic_id and not Mechanic.objects.filter(id=mechanic_id, is_active=True).exists():
        raise BusinessRuleError("Механикът не е намерен.")
    order.mechanic_id, order.mileage_at_service, order.notes = mechanic_id, mileage, clean(notes)
    order.save()
    if not RepairOrder.objects.filter(vehicle_id=order.vehicle_id, opened_on__gt=order.opened_on).exists():
        Vehicle.objects.filter(id=order.vehicle_id).update(mileage=mileage)


def add_service(order_id, service_id, quantity):
    if quantity < 1:
        raise BusinessRuleError("Количеството трябва да е поне 1.")
    if quantity > MAX_SERVICE_QUANTITY:
        raise BusinessRuleError("Количеството е твърде голямо.")
    order = _editable(order_id)
    service = Service.objects.filter(id=service_id).first()
    if service is None:
        raise BusinessRuleError("Услугата не е намерена.")
    # Цената (и съставът на пакета) се „замразяват“ към момента на ремонта.
    _add_line(order, service, quantity, service.price)
    _save_totals(order)


def remove_service(order_id, line_id):
    order = _editable(order_id)
    deleted, _ = order.service_lines.filter(id=line_id).delete()
    if not deleted:
        raise BusinessRuleError("Редът не е намерен.")
    _save_totals(order)


def _unit_text(unit):
    return "л" if unit == PartUnit.LITRE else "бр."


@transaction.atomic
def add_part(order_id, part_id, quantity, choice=PartChoice.MECHANIC_DECIDES, override_reason=None):
    """
    Влага част. Течностите - и дробно количество (4,3 л); частите - цели бройки. Неподходяща за колата част
    се влага само с причина. Донесената от клиента не се изписва от склада и е с цена 0.
    Връща True, ако наличността падне до минимума.
    """
    quantity = Decimal(str(quantity))
    if not quantity.is_finite() or quantity <= 0:
        raise BusinessRuleError("Количеството трябва да е по-голямо от 0.")
    if quantity > MAX_PART_QUANTITY:
        raise BusinessRuleError("Количеството е твърде голямо.")
    if quantity != quantity.quantize(Decimal("0.01")):
        raise BusinessRuleError("Количеството може да е с най-много 2 знака след запетаята.")
    order = _editable(order_id)
    part = Part.objects.prefetch_related("fitments").filter(id=part_id).first()
    if part is None:
        raise BusinessRuleError("Частта не е намерена.")
    if part.unit == PartUnit.PIECE and quantity != quantity.to_integral_value():
        raise BusinessRuleError(f"„{part.name}“ се влага на бройки - цяло число.")

    fit = evaluate_fit(part, vehicle_for_fit(order.vehicle_id))
    if fit.status == FitStatus.DOES_NOT_FIT and not clean(override_reason):
        raise BusinessRuleError(f"„{part.name}“ не е подходяща: {fit.reason} Посочете причина, за да я вложите.")

    supplied = choice == PartChoice.CUSTOMER_SUPPLIED
    if not supplied:
        # Атомарно намаляване: UPDATE … WHERE наличност >= количество.
        # Ако двама вземат последната бройка едновременно, успява само единият.
        updated = Part.objects.filter(id=part_id, quantity_in_stock__gte=quantity) \
            .update(quantity_in_stock=F("quantity_in_stock") - quantity)
        if not updated:
            stock = f"{part.quantity_in_stock.normalize():f}".replace(".", ",")
            raise BusinessRuleError(f"Няма достатъчна наличност от „{part.name}“ (налични: {stock} {_unit_text(part.unit)}).")

    RepairOrderPartLine.objects.create(
        repair_order=order, part=part, quantity=quantity, unit_price_at_time=Decimal(0) if supplied else part.unit_price,
        choice=choice, spec_snapshot=part.spec_summary,
        override_reason=override_reason.strip() if fit.status == FitStatus.DOES_NOT_FIT else None)
    _save_totals(order)
    return not supplied and part.quantity_in_stock - quantity <= part.min_stock_level


@transaction.atomic
def remove_part(order_id, line_id):
    order = _editable(order_id)
    line = order.part_lines.filter(id=line_id).first()
    if line is None:
        raise BusinessRuleError("Редът не е намерен.")
    if line.choice != PartChoice.CUSTOMER_SUPPLIED:  # донесената от клиента не е изписвана
        Part.objects.filter(id=line.part_id).update(quantity_in_stock=F("quantity_in_stock") + line.quantity)
    line.delete()
    _save_totals(order)


@transaction.atomic
def change_status(order_id, status):
    """
    Смяна на етапа. Ремонт с плащане не се връща в работа (сумата не може да падне под платеното).
    Приключва се, когато: има услуги; няма препоръка, която чака клиента; одобрената от клиента работа е отметната
    (иначе - работа, която механикът не е видял, става „изпълнена“). Напълно оценените проверки се публикуват.
    """
    order = RepairOrder.objects.filter(id=order_id).first()
    if order is None:
        raise BusinessRuleError("Ремонтът не е намерен.")
    if status not in RepairStatus.values:
        raise BusinessRuleError("Невалиден статус.")
    if order.status == RepairStatus.PAID:
        raise BusinessRuleError("Ремонтът е платен и не може да се променя.")
    if status == RepairStatus.PAID:
        raise BusinessRuleError("Статус „Платен“ се задава автоматично при пълно плащане.")
    if order.status == RepairStatus.DONE and status != RepairStatus.DONE and order.payments.exists():
        raise BusinessRuleError("По ремонта вече има плащане и не може да се връща в работа. За допълнителна работа отворете нов ремонт.")
    if status == RepairStatus.DONE and order.status != RepairStatus.DONE:
        _ensure_can_finish(order)
    order.status = status
    order.closed_on = datetime.now() if status == RepairStatus.DONE else None
    order.save()
    if status == RepairStatus.DONE:  # приключеният ремонт означава, че всички услуги са изпълнени
        order.service_lines.filter(is_done=False).update(is_done=True, done_on=datetime.now())
        _publish_rated_inspections(order)


def _ensure_can_finish(order):
    if not order.service_lines.exists():
        raise BusinessRuleError("Не може да се приключи ремонт без извършени услуги.")
    waiting = list(order.recommendations.filter(status=RecommendationStatus.PROPOSED).select_related("service"))
    if waiting:
        names = ", ".join(f"„{r.service.name}“" for r in waiting)
        raise BusinessRuleError(f"Препоръка чака решението на клиента ({names}). Ремонтът се приключва, след като клиентът "
                                f"(или рецепцията от негово име) я одобри или откаже.")
    approved = set(order.recommendations.filter(status=RecommendationStatus.APPROVED).values_list("service_id", flat=True))
    unticked = [l for l in order.service_lines.select_related("service").filter(is_done=False) if l.service_id in approved]
    if unticked:
        names = ", ".join(f"„{l.service.name}“" for l in unticked)
        raise BusinessRuleError(f"Клиентът одобри допълнителна работа ({names}), която още не е отметната като изпълнена. "
                                f"Отметнете я, когато е готова, и тогава приключете ремонта.")


def _publish_rated_inspections(order):
    """Проверка с оценени всички точки, но без „Завърши“ - при приключването клиентът я вижда (иначе остава скрита)."""
    for inspection in order.inspections.filter(completed_on__isnull=True):
        if not inspection.results.filter(rating=InspectionRating.UNRATED).exists():
            inspection.completed_on = datetime.now()
            inspection.save(update_fields=["completed_on"])


@transaction.atomic
def add_payment(order_id, amount, method):
    order = RepairOrder.objects.filter(id=order_id).first()
    if order is None:
        raise BusinessRuleError("Ремонтът не е намерен.")
    if order.status != RepairStatus.DONE:
        raise BusinessRuleError("Плащане се приема само за завършен ремонт.")
    amount = round_money(amount)
    remaining = order.remaining_amount
    if amount == 0 and remaining <= 0:
        # Нищо за плащане (напр. безплатна/гаранционна услуга или само донесени от клиента части) - приключва се.
        order.status = RepairStatus.PAID
        order.save(update_fields=["status"])
        return
    if amount <= 0:
        raise BusinessRuleError("Сумата трябва да е положителна.")
    if amount > remaining:
        raise BusinessRuleError(f"Сумата надвишава остатъка за плащане ({str(remaining.quantize(Decimal('0.01'))).replace('.', ',')} €).")
    Payment.objects.create(repair_order=order, amount=amount, method=method, paid_on=datetime.now())
    if order.remaining_amount == 0:  # при пълно изплащане ремонтът става „Платен“
        order.status = RepairStatus.PAID
        order.save(update_fields=["status"])


def set_service_done(order_id, line_id, done):
    order = _editable(order_id)
    line = order.service_lines.filter(id=line_id).first()
    if line is None:
        raise BusinessRuleError("Редът не е намерен.")
    line.is_done, line.done_on = done, datetime.now() if done else None
    line.save()
    if done and order.status == RepairStatus.OPEN:  # първата отметка - работата е започнала
        order.status = RepairStatus.IN_PROGRESS
        order.save(update_fields=["status"])


def assign(order_id, mechanic_id):
    order = _editable(order_id)
    if not Mechanic.objects.filter(id=mechanic_id, is_active=True).exists():
        raise BusinessRuleError("Механикът не е намерен.")
    order.mechanic_id = mechanic_id
    order.save(update_fields=["mechanic"])


def recommend(order_id, service_id, quantity, note):
    if quantity < 1:
        raise BusinessRuleError("Количеството трябва да е поне 1.")
    if quantity > MAX_SERVICE_QUANTITY:
        raise BusinessRuleError("Количеството е твърде голямо.")
    order = _editable(order_id)
    service = Service.objects.filter(id=service_id).first()
    if service is None:
        raise BusinessRuleError("Услугата не е намерена.")
    return Recommendation.objects.create(repair_order=order, service=service, quantity=quantity, price=service.price,
                                         note=clean(note), created_on=datetime.now()).id


@transaction.atomic
def decide_recommendation(recommendation_id, approve, customer_id=None):
    """
    Клиентът (или рецепцията от негово име) одобрява или отказва препоръка. Одобрената се добавя като услуга
    и сумата се преизчислява. С customer_id се проверява, че ремонтът е на този клиент.
    """
    rec = Recommendation.objects.select_related("repair_order__vehicle").filter(id=recommendation_id).first()
    if rec is None or (customer_id is not None and rec.repair_order.customer_id != customer_id):
        raise BusinessRuleError("Препоръката не е намерена.")
    if rec.status != RecommendationStatus.PROPOSED:
        raise BusinessRuleError("По тази препоръка вече има решение.")
    order = rec.repair_order
    # Отказът само записва решението - винаги е възможен. Одобрената работа се добавя към ремонта,
    # затова той трябва още да е в работа.
    if approve and order.status not in OPEN_STATUSES:
        raise BusinessRuleError("Ремонтът вече е приключен - препоръката не може да се добави към него. "
                                "Ако искате тази работа, обадете се в сервиза.")
    rec.status = RecommendationStatus.APPROVED if approve else RecommendationStatus.DECLINED
    rec.decided_on = datetime.now()
    rec.save()
    if approve:
        _add_line(order, rec.service, rec.quantity, rec.price)
        _save_totals(order)
