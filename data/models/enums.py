"""
Изброими типове (статуси, гориво, кутия...). В базата се пазят като текст („Paid“, „Diesel“),
а на екрана се показва българското име.
"""
from django.db import models


class Role:
    """Потребителските роли (групи в Django)."""

    ADMIN = "Admin"
    RECEPTIONIST = "Receptionist"
    MECHANIC = "Mechanic"
    CUSTOMER = "Customer"

    ALL = (ADMIN, RECEPTIONIST, MECHANIC, CUSTOMER)
    STAFF = (ADMIN, RECEPTIONIST, MECHANIC)
    FRONT_DESK = (ADMIN, RECEPTIONIST)
    NAMES = {ADMIN: "Администратор", RECEPTIONIST: "Рецепция", MECHANIC: "Механик", CUSTOMER: "Клиент"}


class FuelType(models.TextChoices):
    PETROL = "Petrol", "Бензин"
    DIESEL = "Diesel", "Дизел"
    LPG = "Lpg", "Газ (LPG)"
    HYBRID = "Hybrid", "Хибрид"
    ELECTRIC = "Electric", "Електрически"
    UNKNOWN = "Unknown", "Не знам"


class Transmission(models.TextChoices):
    """Скоростна кутия - не е в талона, но променя маслото и цената на обслужването."""

    UNKNOWN = "Unknown", "Не знам"
    MANUAL = "Manual", "Ръчна"
    AUTOMATIC = "Automatic", "Автоматична"
    DUAL_CLUTCH = "DualClutch", "С двоен съединител (DSG)"
    CVT = "Cvt", "Безстепенна (CVT)"


class AppointmentStatus(models.TextChoices):
    PENDING = "Pending", "Чакащ"
    CONFIRMED = "Confirmed", "Потвърден"
    CANCELLED = "Cancelled", "Отказан"
    COMPLETED = "Completed", "Изпълнен"


class RepairStatus(models.TextChoices):
    OPEN = "Open", "Отворен"
    IN_PROGRESS = "InProgress", "В процес"
    DONE = "Done", "Завършен"
    PAID = "Paid", "Платен"


# Редът на етапите на ремонта (за сравнения „поне В процес“ и за проследяването при клиента).
REPAIR_STEPS = [RepairStatus.OPEN, RepairStatus.IN_PROGRESS, RepairStatus.DONE, RepairStatus.PAID]


class PaymentMethod(models.TextChoices):
    CASH = "Cash", "В брой"
    CARD = "Card", "С карта"
    BANK_TRANSFER = "BankTransfer", "Банков превод"


class RecommendationStatus(models.TextChoices):
    PROPOSED = "Proposed", "Предложена"
    APPROVED = "Approved", "Одобрена"
    DECLINED = "Declined", "Отказана"


class ServiceCategory(models.TextChoices):
    MAINTENANCE = "Maintenance", "Обслужване"
    BRAKES = "Brakes", "Спирачки"
    SUSPENSION = "Suspension", "Ходова част"
    TYRES = "Tyres", "Гуми"
    AIR_CONDITIONING = "AirConditioning", "Климатик"
    ENGINE = "Engine", "Двигател"
    ELECTRICAL = "Electrical", "Електрика и диагностика"


class PartUnit(models.TextChoices):
    PIECE = "Piece", "бр."
    LITRE = "Litre", "л"


class FluidKind(models.TextChoices):
    ENGINE_OIL = "EngineOil", "Двигателно масло"
    TRANSMISSION_FLUID = "TransmissionFluid", "Масло за скоростна кутия"


class PartChoice(models.TextChoices):
    """Кой е избрал частта - пази се във всеки ред на ремонта."""

    MECHANIC_DECIDES = "MechanicDecides", "Избрана от механика"
    CUSTOMER_SELECTED = "CustomerSelected", "По избор на клиента"
    CUSTOMER_SUPPLIED = "CustomerSupplied", "Предоставена от клиента"


class FitStatus(models.TextChoices):
    FITS = "Fits", "Подходяща"
    UNKNOWN = "Unknown", "Неизвестно"
    DOES_NOT_FIT = "DoesNotFit", "Неподходяща"


FIT_ORDER = [FitStatus.FITS, FitStatus.UNKNOWN, FitStatus.DOES_NOT_FIT]


class PartsPreference(models.TextChoices):
    MECHANIC_DECIDES = "MechanicDecides", "Механикът да избере подходящите"
    CUSTOMER_HAS_PREFERENCE = "CustomerHasPreference", "Имам предпочитание"
    CUSTOMER_BRINGS_OWN = "CustomerBringsOwn", "Ще донеса свои части/масло"


class InspectionItemType(models.TextChoices):
    RATING = "Rating", "Оценка"
    MEASUREMENT = "Measurement", "Измерване"
    YES_NO = "YesNo", "Да / не"


class InspectionRating(models.TextChoices):
    UNRATED = "Unrated", "Не е проверено"
    GREEN = "Green", "Добре"
    YELLOW = "Yellow", "Скоро"
    RED = "Red", "Спешно"
    NOT_APPLICABLE = "NotApplicable", "Неприложимо"


class InspectionScale(models.TextChoices):
    """„Преди ГТП“ следва Директива 2014/45/ЕС: незначителен (минава), значителен (не минава), опасен."""

    STANDARD = "Standard", "Добре / Скоро / Спешно"
    ROADWORTHINESS = "RoadworthinessDefects", "Дефекти по ГТП"


def parse_choice(choices, raw, default=None):
    """
    Стойност от формата → изброим тип. Приема името („Diesel“) или поредния номер („1“).
    """
    if raw is None or str(raw).strip() == "":
        return default
    raw = str(raw).strip()
    for value in choices.values:
        if value.lower() == raw.lower():
            return value
    if raw.isdigit() and int(raw) < len(choices.values):
        return choices.values[int(raw)]
    return default
