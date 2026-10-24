"""Дигитална проверка: шаблони с точки, проверки, резултати и снимки."""
from django.db import models
from django.utils import timezone

from .catalog import Service
from .enums import InspectionItemType, InspectionRating, InspectionScale
from .people import Mechanic
from .repairs import RepairOrder


class InspectionTemplate(models.Model):
    """Шаблон за проверка (напр. „Стандартна проверка“, „Проверка преди ГТП“)."""

    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True, null=True)
    scale = models.CharField(max_length=30, choices=InspectionScale.choices, default=InspectionScale.STANDARD)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class InspectionTemplateItem(models.Model):
    """Точка от шаблона: раздел, име, вид и прагове за измерване."""

    template = models.ForeignKey(InspectionTemplate, on_delete=models.CASCADE, related_name="items")
    section = models.CharField(max_length=40)   # Гуми, Спирачки, Течности...
    name = models.CharField(max_length=80)
    hint = models.CharField(max_length=200, blank=True, null=True)
    type = models.CharField(max_length=20, choices=InspectionItemType.choices, default=InspectionItemType.RATING)
    unit = models.CharField(max_length=10, blank=True, null=True)  # „мм“, „%“
    # Под warn_below - жълто (грайфер под 3 мм); под fail_below - червено (под 1,6 мм).
    warn_below = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fail_below = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    # Услугата, която се предлага при „Препоръчай“ (напр. смяна на накладки).
    suggested_service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    sort_order = models.IntegerField(default=0)


class Inspection(models.Model):
    """Дигитална проверка на автомобила по време на ремонт."""

    repair_order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="inspections")
    template = models.ForeignKey(InspectionTemplate, on_delete=models.PROTECT, related_name="+")
    mechanic = models.ForeignKey(Mechanic, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    started_on = models.DateTimeField(default=timezone.now)
    # Попълва се при „Завърши проверката“ - едва тогава клиентът я вижда.
    completed_on = models.DateTimeField(null=True, blank=True)

    @property
    def is_completed(self):
        return self.completed_on is not None

    def count(self, rating):
        return sum(1 for r in self.results.all() if r.rating == rating)


class InspectionResult(models.Model):
    """Резултат за една точка: оценка, измерване, бележка и снимки."""

    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="results")
    template_item = models.ForeignKey(InspectionTemplateItem, on_delete=models.PROTECT, related_name="+")
    rating = models.CharField(max_length=20, choices=InspectionRating.choices, default=InspectionRating.UNRATED)
    measurement = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, null=True)


class InspectionPhoto(models.Model):
    """
    Снимка към точка от проверката. Файлът е извън static и се отдава само през изглед
    с проверка на правата - клиентът вижда само снимките на своя автомобил.
    """

    result = models.ForeignKey(InspectionResult, on_delete=models.CASCADE, related_name="photos")
    file_name = models.CharField(max_length=80)  # случаен uuid + разширение
    content_type = models.CharField(max_length=40, default="image/jpeg")
    uploaded_on = models.DateTimeField(default=timezone.now)
