"""Двигатели, течности и съвместимост на частите."""
from dataclasses import dataclass

from django.db import transaction

from data.models import (EngineVariant, FitStatus, FIT_ORDER, FluidKind, FluidRequirement, FuelType, Part,
                         Transmission, Vehicle)

from .common import BusinessRuleError


@dataclass
class FitResult:
    status: str
    reason: str | None
    suggested_quantity: object | None  # Decimal - литрите по изискването


def _approvals(text):
    """„VW 504.00, vw 507.00“ → {„VW 504.00“, „VW 507.00“} - без значение от главни/малки и интервали."""
    return {" ".join(a.split()).upper() for a in (text or "").split(",") if a.strip()}


def evaluate_fit(part, vehicle, fitment_engine_ids=None):
    """
    Подходяща ли е частта за автомобила:
    - течност: изискване от същия вид (за кутия - при същия тип кутия), същият вискозитет и поне едно общо одобрение;
    - универсална част - подходяща за всички;
    - друга част: подходяща, ако е отбелязана за двигателя; „неизвестно“, ако двигателят не е известен
      или частта няма данни за съвместимост.
    """
    if part.is_universal:
        return FitResult(FitStatus.FITS, None, None)
    engine = vehicle.engine_variant
    if part.fluid_kind:
        if engine is None:
            return FitResult(FitStatus.UNKNOWN, "Двигателят не е избран - проверете изискванията.", None)
        requirement = next((f for f in engine.fluids.all() if f.kind == part.fluid_kind
                            and (part.fluid_kind == FluidKind.ENGINE_OIL or f.transmission == vehicle.transmission)), None)
        if requirement is None:
            if part.fluid_kind == FluidKind.TRANSMISSION_FLUID and vehicle.transmission == Transmission.UNKNOWN:
                return FitResult(FitStatus.UNKNOWN, "Типът скоростна кутия не е известен.", None)
            return FitResult(FitStatus.UNKNOWN, "Няма данни за изискванията на този автомобил.", None)
        if requirement.viscosity and part.viscosity and requirement.viscosity.lower() != part.viscosity.lower():
            return FitResult(FitStatus.DOES_NOT_FIT, f"Изисква {requirement.viscosity}, а това е {part.viscosity}.",
                             requirement.capacity_litres)
        if _approvals(requirement.approvals) & _approvals(part.approvals):
            return FitResult(FitStatus.FITS, None, requirement.capacity_litres)
        return FitResult(FitStatus.DOES_NOT_FIT, f"Изисква {requirement.approvals}.", requirement.capacity_litres)

    engine_ids = fitment_engine_ids if fitment_engine_ids is not None else {f.engine_variant_id for f in part.fitments.all()}
    if not engine_ids:
        return FitResult(FitStatus.UNKNOWN, None, None)
    if engine is None:
        return FitResult(FitStatus.UNKNOWN, "Двигателят не е избран.", None)
    if engine.id in engine_ids:
        return FitResult(FitStatus.FITS, None, None)
    return FitResult(FitStatus.DOES_NOT_FIT, f"Не е отбелязана за {engine.name}.", None)


def vehicle_for_fit(vehicle_id):
    vehicle = Vehicle.objects.select_related("engine_variant").prefetch_related("engine_variant__fluids") \
        .filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")
    return vehicle


@dataclass
class PartOption:
    part: Part
    fit: FitResult


def part_options(vehicle_id):
    """Частите в наличност, подредени: подходящи, неизвестни, неподходящи."""
    vehicle = vehicle_for_fit(vehicle_id)
    parts = Part.objects.prefetch_related("fitments").filter(quantity_in_stock__gt=0).order_by("name")
    options = [PartOption(p, evaluate_fit(p, vehicle)) for p in parts]
    return sorted(options, key=lambda o: (FIT_ORDER.index(o.fit.status), o.part.name))


# ---------------------------------------------------------------------------- каталог с двигатели
def all_engines():
    return list(EngineVariant.objects.prefetch_related("fluids").order_by("makes", "name"))


def get(engine_id):
    return EngineVariant.objects.prefetch_related("fluids").filter(id=engine_id).first()


@transaction.atomic
def save(engine, fluids):
    """Записва двигателя и изискванията му (заменят старите). fluids - списък от FluidRequirement без двигател."""
    if any(f.capacity_litres is None or f.capacity_litres <= 0 or not (f.approvals or "").strip() for f in fluids):
        raise BusinessRuleError("Всяка течност трябва да има одобрения и количество.")
    if any(f.capacity_litres > 50 for f in fluids):
        raise BusinessRuleError("Количеството течност трябва да е до 50 л.")
    engine.save()
    engine.fluids.all().delete()
    for fluid in fluids:
        fluid.engine_variant = engine
        fluid.save()
    return engine


def delete(engine_id):
    engine = EngineVariant.objects.filter(id=engine_id).first()
    if engine is None:
        raise BusinessRuleError("Двигателят не е намерен.")
    if Vehicle.objects.filter(engine_variant=engine).exists():
        raise BusinessRuleError("Има автомобили с този двигател - не може да се изтрие.")
    engine.delete()


@dataclass
class EngineSuggestion:
    engine: EngineVariant
    matches_registration: bool


def suggest(vehicle_id):
    """Двигатели за марката - първо съвпадащите с талона (гориво, обем ± 60, мощност ± 5 kW)."""
    vehicle = Vehicle.objects.filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")

    def matches(e):
        return (e.fuel_type == vehicle.fuel_type
                and (vehicle.engine_cc is None or abs(e.displacement_cc - vehicle.engine_cc) <= 60)
                and (vehicle.power_kw is None or abs(e.power_kw - vehicle.power_kw) <= 5))

    suggestions = [EngineSuggestion(e, matches(e)) for e in all_engines() if e.applies_to(vehicle.make)]
    return sorted(suggestions, key=lambda s: (not s.matches_registration, s.engine.name))


def set_vehicle_engine(vehicle_id, engine_id):
    vehicle = Vehicle.objects.filter(id=vehicle_id).first()
    if vehicle is None:
        raise BusinessRuleError("Автомобилът не е намерен.")
    if engine_id:
        engine = EngineVariant.objects.filter(id=engine_id).first()
        if engine is None:
            raise BusinessRuleError("Двигателят не е намерен.")
        # Липсващите данни от талона се попълват от двигателя.
        vehicle.engine_cc = vehicle.engine_cc or engine.displacement_cc
        vehicle.power_kw = vehicle.power_kw or engine.power_kw
        if vehicle.fuel_type == FuelType.UNKNOWN:
            vehicle.fuel_type = engine.fuel_type
    vehicle.engine_variant_id = engine_id or None
    vehicle.save()
