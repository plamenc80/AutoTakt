"""Дигитална проверка и снимките към нея."""
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch

from data.models import (Inspection, InspectionItemType, InspectionPhoto, InspectionRating, InspectionResult,
                         InspectionTemplate, Recommendation, RecommendationStatus, RepairOrder, RepairStatus)

from . import repairs
from .common import BusinessRuleError, clean

MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTOS_PER_ITEM = 6


# ---------------------------------------------------------------------------- хранилище за снимки
class PhotoStore:
    """
    Снимките се пазят в папка извън static (private/photos), затова нямат директен адрес -
    отдават се само през изглед, който проверява правата.
    """

    def __init__(self, root=None):
        self.root = Path(root or settings.PHOTO_ROOT)

    def save(self, data, extension):
        self.root.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{extension}"
        (self.root / name).write_bytes(data)
        return name

    def open(self, name):
        path = self.root / Path(name).name  # Path(...).name - без „../“
        return path.open("rb") if path.exists() else None

    def delete(self, name):
        (self.root / Path(name).name).unlink(missing_ok=True)


def photo_store():
    return PhotoStore()


def detect_image(data):
    """JPEG, PNG и WebP по „магическите“ първи байтове - видът се проверява по съдържанието, не по името."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


# ---------------------------------------------------------------------------- правила
def evaluate(item, value):
    """Оценка по измерване: под прага „червено“ - Спешно, под „жълто“ - Скоро, иначе Добре (накладки 2,5 мм → Скоро)."""
    if item.fail_below is not None and value < item.fail_below:
        return InspectionRating.RED
    if item.warn_below is not None and value < item.warn_below:
        return InspectionRating.YELLOW
    return InspectionRating.GREEN


def _ensure_open(order):
    if order.status in (RepairStatus.DONE, RepairStatus.PAID):
        raise BusinessRuleError("Ремонтът е приключен - проверката не може да се променя.")


def templates():
    return list(InspectionTemplate.objects.filter(is_active=True).prefetch_related("items").order_by("id"))


def get(inspection_id):
    results = (InspectionResult.objects.select_related("template_item__suggested_service")
               .prefetch_related("photos").order_by("template_item__sort_order"))
    return (Inspection.objects.select_related("template", "mechanic", "repair_order__vehicle__customer", "repair_order__customer")
            .prefetch_related(Prefetch("results", results), "repair_order__recommendations")
            .filter(id=inspection_id).first())


def for_order(order_id):
    results = InspectionResult.objects.select_related("template_item").prefetch_related("photos")
    return list(Inspection.objects.select_related("template").prefetch_related(Prefetch("results", results))
                .filter(repair_order_id=order_id).order_by("started_on"))


@transaction.atomic
def start(order_id, template_id, mechanic_id):
    """Започва проверка по шаблон; ако вече има такава за ремонта - връща нея."""
    order = RepairOrder.objects.filter(id=order_id).first()
    if order is None:
        raise BusinessRuleError("Ремонтът не е намерен.")
    _ensure_open(order)
    template = InspectionTemplate.objects.filter(id=template_id, is_active=True).first()
    if template is None:
        raise BusinessRuleError("Шаблонът за проверка не е намерен.")
    existing = Inspection.objects.filter(repair_order=order, template=template).first()
    if existing:
        return existing.id
    inspection = Inspection.objects.create(repair_order=order, template=template,
                                           mechanic_id=mechanic_id or order.mechanic_id, started_on=datetime.now())
    InspectionResult.objects.bulk_create([InspectionResult(inspection=inspection, template_item=item)
                                          for item in template.items.order_by("sort_order")])
    return inspection.id


def _editable_result(result_id):
    result = (InspectionResult.objects.select_related("template_item", "inspection__repair_order")
              .prefetch_related("photos").filter(id=result_id).first())
    if result is None:
        raise BusinessRuleError("Точката от проверката не е намерена.")
    _ensure_open(result.inspection.repair_order)
    return result


def save_result(result_id, rating=None, measurement=None, note=None):
    """
    Оценка, измерване и/или бележка за точка. При измерване оценката се изчислява сама - по стойността,
    закръглена както се пази и показва (2 знака). Точка, поправена на „Добре“ или „Н/П“, оттегля
    препоръката си, докато клиентът още не е решил.
    """
    result = _editable_result(result_id)
    item = result.template_item
    if measurement is not None:
        if item.type != InspectionItemType.MEASUREMENT:
            raise BusinessRuleError("Тази точка не се измерва.")
        if measurement < 0 or measurement > 1000:
            raise BusinessRuleError("Невалидна стойност на измерването.")
        measurement = Decimal(measurement).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result.measurement = measurement
        result.rating = evaluate(item, measurement)
    elif rating:
        if rating == InspectionRating.UNRATED:
            raise BusinessRuleError("Изберете оценка.")  # оценена точка не може да стане отново „непроверена“
        if item.type == InspectionItemType.YES_NO and rating == InspectionRating.YELLOW:
            raise BusinessRuleError("Тази точка е „наред / не е наред“.")
        result.rating = rating
        if item.type == InspectionItemType.MEASUREMENT and rating == InspectionRating.NOT_APPLICABLE:
            result.measurement = None
    if note is not None:
        result.note = clean(note)
    result.save()
    if result.rating in (InspectionRating.GREEN, InspectionRating.NOT_APPLICABLE):
        Recommendation.objects.filter(inspection_result=result, status=RecommendationStatus.PROPOSED).delete()
    return result


def add_photo(result_id, data, store=None):
    result = _editable_result(result_id)
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise BusinessRuleError("Снимката трябва да е до 8 MB.")
    if result.photos.count() >= MAX_PHOTOS_PER_ITEM:
        raise BusinessRuleError(f"До {MAX_PHOTOS_PER_ITEM} снимки на точка.")
    detected = detect_image(data)
    if detected is None:
        raise BusinessRuleError("Позволени са само снимки (JPEG, PNG или WebP).")
    content_type, extension = detected
    name = (store or photo_store()).save(data, extension)
    return InspectionPhoto.objects.create(result=result, file_name=name, content_type=content_type, uploaded_on=datetime.now())


def delete_photo(photo_id, store=None):
    photo = InspectionPhoto.objects.filter(id=photo_id).first()
    if photo is None:
        raise BusinessRuleError("Снимката не е намерена.")
    _editable_result(photo.result_id)
    photo.delete()
    (store or photo_store()).delete(photo.file_name)


def get_photo(photo_id):
    return InspectionPhoto.objects.select_related("result__inspection__repair_order__vehicle").filter(id=photo_id).first()


def visible_to_customer(photo, customer_id):
    """Клиентът вижда снимка само от своя автомобил и само от завършена проверка (или точка с препоръка)."""
    inspection = photo.result.inspection
    if inspection.repair_order.customer_id != customer_id:
        return False
    return inspection.is_completed or Recommendation.objects.filter(inspection_result_id=photo.result_id).exists()


def recommend(result_id, service_id, note=None):
    """„Препоръчай“ от жълта/червена точка - препоръката носи измерването, бележката и снимките."""
    result = _editable_result(result_id)
    if result.rating not in (InspectionRating.YELLOW, InspectionRating.RED):
        raise BusinessRuleError("Препоръка се прави само за точка, оценена „Скоро“ или „Спешно“.")
    if Recommendation.objects.filter(inspection_result=result).exclude(status=RecommendationStatus.DECLINED).exists():
        raise BusinessRuleError("За тази точка вече има препоръка.")
    item = result.template_item
    measured = ""
    if result.measurement is not None:
        value = f"{result.measurement.normalize():f}".replace(".", ",")  # винаги десетична запетая
        measured = f" - {value} {item.unit or ''}".rstrip()
    text = f"Проверка: {item.name}{measured}."
    extra = clean(note) or result.note
    if extra:
        text += " " + extra
    rec_id = repairs.recommend(result.inspection.repair_order_id, service_id, 1, text[:500])
    Recommendation.objects.filter(id=rec_id).update(inspection_result=result)
    return rec_id


def complete(inspection_id):
    """Завършва проверката - всички точки трябва да са оценени; от този момент клиентът я вижда."""
    inspection = Inspection.objects.select_related("repair_order").filter(id=inspection_id).first()
    if inspection is None:
        raise BusinessRuleError("Проверката не е намерена.")
    _ensure_open(inspection.repair_order)
    unrated = inspection.results.filter(rating=InspectionRating.UNRATED).count()
    if unrated:
        raise BusinessRuleError("Остава 1 непроверена точка." if unrated == 1 else f"Остават {unrated} непроверени точки.")
    if inspection.completed_on is None:
        inspection.completed_on = datetime.now()
        inspection.save(update_fields=["completed_on"])


def order_id_for_result(result_id):
    return InspectionResult.objects.filter(id=result_id).values_list("inspection__repair_order_id", flat=True).first()


def parse_measurement(raw):
    """„2,5“ или „2.5“ → Decimal; празно → None."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = Decimal(str(raw).strip().replace(",", "."))
    except ArithmeticError:
        raise BusinessRuleError("Невалидна стойност на измерването.")
    if not value.is_finite():  # „NaN“, „Infinity“
        raise BusinessRuleError("Невалидна стойност на измерването.")
    return value
