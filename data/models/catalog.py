"""Ценоразпис (услуги и пакети) и склад (части, съвместимост)."""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .enums import FluidKind, PartUnit, ServiceCategory
from .vehicles import EngineVariant

MONEY = {"max_digits": 12, "decimal_places": 2}


class Service(models.Model):
    """Услуга от ценоразписа (напр. „Смяна на масло“) или пакет от услуги."""

    name = models.CharField("Услуга", max_length=100)
    description = models.CharField("Описание", max_length=500, blank=True, null=True)
    price = models.DecimalField("Цена (€)", validators=[MinValueValidator(0), MaxValueValidator(100_000)], **MONEY)
    estimated_hours = models.DecimalField("Очаквано време (ч)", max_digits=6, decimal_places=2, default=0,
                                          validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_active = models.BooleanField("Активна", default=True)

    # Интервал на обслужване - за „здравето“ на автомобила (кога наближава следващото).
    interval_km = models.IntegerField("Интервал (км)", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(500_000)])
    interval_months = models.IntegerField("Интервал (месеца)", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(240)])

    category = models.CharField("Категория", max_length=20, choices=ServiceCategory.choices, default=ServiceCategory.MAINTENANCE)
    is_featured = models.BooleanField("Сред най-търсените", default=False)
    sort_order = models.IntegerField("Подредба", default=0, validators=[MinValueValidator(0), MaxValueValidator(1000)])
    image_url = models.CharField("Снимка (адрес)", max_length=300, blank=True, null=True)
    is_package = models.BooleanField("Пакет от услуги", default=False)
    badge = models.CharField("Етикет (напр. „Най-избирано“)", max_length=40, blank=True, null=True)

    @property
    def has_interval(self):
        return (self.interval_km or 0) > 0 or (self.interval_months or 0) > 0

    @property
    def included_summary(self):
        """„Масло и филтър, диагностика, …“ - за реда на пакета в ремонта и протокола."""
        return ", ".join(item.service.name for item in self.package_items.all())

    def __str__(self):
        return self.name


class ServicePackageItem(models.Model):
    """Услуга, включена в пакет (много-към-много между пакета и услугите)."""

    package = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="package_items")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")


class Part(models.Model):
    """Авточаст или течност в склада."""

    name = models.CharField("Част", max_length=100)
    part_number = models.CharField("Каталожен №", max_length=50, unique=True)
    manufacturer = models.CharField("Производител", max_length=100, blank=True, null=True)
    unit_price = models.DecimalField("Ед. цена (€)", validators=[MinValueValidator(0), MaxValueValidator(100_000)], **MONEY)
    quantity_in_stock = models.DecimalField("Наличност", max_digits=10, decimal_places=2, default=0,
                                            validators=[MinValueValidator(0), MaxValueValidator(100_000)])
    min_stock_level = models.IntegerField("Мин. наличност", default=0, validators=[MinValueValidator(0), MaxValueValidator(10_000)])
    unit = models.CharField("Мерна единица", max_length=10, choices=PartUnit.choices, default=PartUnit.PIECE)

    # Ако частта е течност - вид, вискозитет и одобрения (за проверка на съвместимостта).
    fluid_kind = models.CharField("Вид течност", max_length=20, choices=FluidKind.choices, blank=True, null=True)
    viscosity = models.CharField("Вискозитет", max_length=10, blank=True, null=True)
    approvals = models.CharField("Одобрения / спецификации", max_length=200, blank=True, null=True)
    is_universal = models.BooleanField("Универсална", default=False)

    @property
    def is_low_stock(self):
        return self.quantity_in_stock <= self.min_stock_level

    @property
    def spec_summary(self):
        """„5W-30 · VW 504.00, VW 507.00“ - записва се в реда на ремонта като история."""
        if not self.fluid_kind:
            return None
        return " · ".join(x for x in (self.viscosity, self.approvals) if x and x.strip())

    def __str__(self):
        return self.name


class PartFitment(models.Model):
    """Част, подходяща за даден двигател (много-към-много)."""

    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="fitments")
    engine_variant = models.ForeignKey(EngineVariant, on_delete=models.CASCADE, related_name="fitments")

    class Meta:
        unique_together = [("part", "engine_variant")]
