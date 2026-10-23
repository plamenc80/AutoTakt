"""Записани часове, ремонти, вложени услуги и части, плащания и препоръки."""
from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .catalog import MONEY, Part, Service
from .enums import (AppointmentStatus, PartChoice, PartsPreference, PaymentMethod, RecommendationStatus,
                    RepairStatus)
from .people import Customer, Mechanic
from .vehicles import Vehicle

VAT_RATE = Decimal("0.20")  # ДДС в България - 20%
CENT = Decimal("0.01")


def round_money(value):
    """
    Търговско закръгляне до цент (0,005 → 0,01). Същото закръгляне се ползва и при показването на сумите,
    затова редовете в протокола винаги дават сумата отдолу.
    """
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class Appointment(models.Model):
    """Записан час за ремонт."""

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="appointments", verbose_name="Клиент")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="appointments", verbose_name="Автомобил")
    scheduled_for = models.DateTimeField("Дата и час")
    description = models.CharField("Описание на проблема", max_length=500)
    # Заявена услуга - добавя се автоматично в ремонта при приемане на автомобила.
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Услуга")
    status = models.CharField("Статус", max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING)
    # Записване от гост, което рецепцията трябва да провери (напр. номерът е на друг клиент).
    needs_review = models.BooleanField(default=False)
    review_note = models.CharField(max_length=300, blank=True, null=True)
    parts_preference = models.CharField("Части и масла", max_length=30, choices=PartsPreference.choices,
                                        default=PartsPreference.MECHANIC_DECIDES)
    parts_note = models.CharField("Предпочитание за частите", max_length=300, blank=True, null=True)
    is_guest_booking = models.BooleanField(default=False)
    created_on = models.DateTimeField(default=timezone.now)


class RepairOrder(models.Model):
    """Ремонт (работна карта) на конкретен автомобил."""

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="repair_orders", verbose_name="Автомобил")
    # Клиентът, за когото е ремонтът (собственикът към момента). При продажба на колата старите протоколи остават
    # на него - „Моят гараж“ и протоколът ползват това поле, а не текущия собственик на колата.
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True, related_name="repair_orders",
                                 verbose_name="Клиент")
    mechanic = models.ForeignKey(Mechanic, on_delete=models.SET_NULL, null=True, blank=True, related_name="repair_orders",
                                 verbose_name="Механик")
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    opened_on = models.DateTimeField("Отворен на", default=timezone.now)
    closed_on = models.DateTimeField("Приключен на", null=True, blank=True)
    status = models.CharField("Статус", max_length=20, choices=RepairStatus.choices, default=RepairStatus.OPEN)
    mileage_at_service = models.IntegerField("Пробег при приемане", default=0,
                                             validators=[MinValueValidator(0), MaxValueValidator(3_000_000)])
    notes = models.CharField("Бележки", max_length=1000, blank=True, null=True)

    # Изчислени суми - пазят се, за да не се преизчисляват при всяка справка.
    total_labor = models.DecimalField("Труд (€)", default=0, **MONEY)
    total_parts = models.DecimalField("Части (€)", default=0, **MONEY)
    vat = models.DecimalField("ДДС (€)", default=0, **MONEY)
    total_amount = models.DecimalField("Общо (€)", default=0, **MONEY)

    parts_preference = models.CharField("Части и масла", max_length=30, choices=PartsPreference.choices,
                                        default=PartsPreference.MECHANIC_DECIDES)
    parts_note = models.CharField("Предпочитание за частите", max_length=300, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.customer_id is None and self.vehicle_id:
            self.customer_id = self.vehicle.customer_id  # по подразбиране - собственикът на колата към момента
        super().save(*args, **kwargs)

    @property
    def client(self):
        """Клиентът по ремонта (за стари записи без него - собственикът на колата)."""
        return self.customer if self.customer_id else self.vehicle.customer

    def recalculate_totals(self):
        """
        Стойността на ремонта: труд = Σ(брой × цена на услугата), части = Σ(брой × ед. цена),
        ДДС = 20% от (труд + части), общо = труд + части + ДДС. Всеки ред се закръгля до стотинка, както се показва
        в протокола - така редовете винаги дават сумата отдолу (3,75 л × 10,50 € = 39,38 €, а не 39,375).
        """
        self.total_labor = sum((round_money(line.line_total) for line in self.service_lines.all()), Decimal(0))
        self.total_parts = sum((round_money(line.line_total) for line in self.part_lines.all()), Decimal(0))
        self.vat = round_money((self.total_labor + self.total_parts) * VAT_RATE)
        self.total_amount = self.total_labor + self.total_parts + self.vat

    @property
    def done_services_count(self):
        """Колко от услугите са отметнати като изпълнени (за прогреса в таблото)."""
        return sum(1 for line in self.service_lines.all() if line.is_done)

    @property
    def paid_amount(self):
        return sum((p.amount for p in self.payments.all()), Decimal(0))

    @property
    def remaining_amount(self):
        return self.total_amount - self.paid_amount

    @property
    def tax_base(self):
        """Данъчна основа (труд + части, без ДДС)."""
        return self.total_labor + self.total_parts

    @property
    def has_customer_supplied_parts(self):
        return any(p.choice == PartChoice.CUSTOMER_SUPPLIED for p in self.part_lines.all())


class RepairOrderServiceLine(models.Model):
    """Извършена услуга по ремонт (много-към-много между ремонт и услуга)."""

    repair_order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="service_lines")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField(default=1)
    # Цената в момента на ремонта - историята не се променя, ако после се смени ценоразписът.
    price_at_time = models.DecimalField(**MONEY)
    # Механикът отбелязва услугата като изпълнена (отметка в таблото).
    is_done = models.BooleanField(default=False)
    done_on = models.DateTimeField(null=True, blank=True)
    # Съставът на пакета към момента на ремонта ([[id на услуга, име], ...]) - после промяна на пакета
    # в ценоразписа не пренаписва протоколите и историята.
    package_items = models.JSONField(default=list, blank=True)

    @property
    def line_total(self):
        return self.quantity * self.price_at_time

    @property
    def included_summary(self):
        """„Масло и филтър, диагностика, …“ - какво е включвал пакетът при този ремонт."""
        if self.package_items:
            return ", ".join(name for _, name in self.package_items)
        return self.service.included_summary if self.service.is_package else ""

    @property
    def included_service_ids(self):
        if self.package_items:
            return [service_id for service_id, _ in self.package_items]
        return [i.service_id for i in self.service.package_items.all()] if self.service.is_package else []


class RepairOrderPartLine(models.Model):
    """Вложена част в ремонт. Течностите се влагат в литри (4,3 л)."""

    repair_order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="part_lines")
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price_at_time = models.DecimalField(**MONEY)
    # Кой е избрал частта. „Предоставена от клиента“ - цена 0 и без гаранция за частта.
    choice = models.CharField(max_length=20, choices=PartChoice.choices, default=PartChoice.MECHANIC_DECIDES)
    # Спецификацията към момента (напр. „5W-30 · VW 507.00“) - остава в историята.
    spec_snapshot = models.CharField(max_length=200, blank=True, null=True)
    # Защо е вложена част, отбелязана като неподходяща за автомобила.
    override_reason = models.CharField(max_length=200, blank=True, null=True)

    @property
    def line_total(self):
        return self.quantity * self.unit_price_at_time


class Payment(models.Model):
    repair_order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField("Сума (€)", validators=[MinValueValidator(Decimal("0.01"))], **MONEY)
    method = models.CharField("Начин на плащане", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    paid_on = models.DateTimeField("Дата", default=timezone.now)


class Recommendation(models.Model):
    """
    Препоръка за допълнителна работа, открита от механика по време на ремонта
    (напр. „спирачните дискове са под минималната дебелина“). Клиентът я одобрява или отказва онлайн.
    """

    repair_order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="recommendations")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(**MONEY)  # без ДДС към момента на препоръката
    note = models.CharField("Бележка от механика", max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=RecommendationStatus.choices, default=RecommendationStatus.PROPOSED)
    created_on = models.DateTimeField(default=timezone.now)
    decided_on = models.DateTimeField(null=True, blank=True)
    # Точката от проверката, от която е направена - клиентът вижда снимките ѝ.
    inspection_result = models.ForeignKey("InspectionResult", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    @property
    def total(self):
        return self.quantity * self.price
