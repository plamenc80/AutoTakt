"""Автомобили, марки/модели и двигатели с изискванията им за течности."""
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from .enums import FluidKind, FuelType, Transmission
from .people import Customer

VIN_VALIDATOR = RegexValidator(
    r"^[A-HJ-NPR-Za-hj-npr-z0-9]{17}$",
    "VIN трябва да съдържа точно 17 символа (латински букви без I, O, Q и цифри).",
)


class CarMake(models.Model):
    """Марка - за подсказките при въвеждане (може да се напише и марка, която я няма тук)."""

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class CarModel(models.Model):
    make = models.ForeignKey(CarMake, on_delete=models.CASCADE, related_name="models")
    name = models.CharField(max_length=50)


class EngineVariant(models.Model):
    """Вариант на двигателя (напр. „1.6 TDI, 77 kW“) с изискванията за масло и течности."""

    makes = models.CharField("Марки", max_length=120)  # „Volkswagen, VW, Skoda, Seat, Audi“
    name = models.CharField("Двигател", max_length=60)
    engine_code = models.CharField("Код на двигателя (P.5)", max_length=20, blank=True, null=True)
    fuel_type = models.CharField("Гориво", max_length=20, choices=FuelType.choices, default=FuelType.DIESEL)
    displacement_cc = models.IntegerField("Работен обем, куб. см", validators=[MinValueValidator(50), MaxValueValidator(10_000)])
    power_kw = models.IntegerField("Мощност, kW", validators=[MinValueValidator(1), MaxValueValidator(1_500)])

    @property
    def display_name(self):
        code = f" ({self.engine_code})" if self.engine_code else ""
        return f"{self.name}{code}, {self.power_kw} kW"

    def applies_to(self, make):
        """Среща ли се двигателят при тази марка (VW = Volkswagen)."""
        if not make or not make.strip():
            return False
        return make.strip().lower() in [m.strip().lower() for m in self.makes.split(",") if m.strip()]

    def __str__(self):
        return self.display_name


class FluidRequirement(models.Model):
    """Изискване за течност: вискозитет, одобрения (поне едно да е изпълнено) и количество."""

    engine_variant = models.ForeignKey(EngineVariant, on_delete=models.CASCADE, related_name="fluids")
    kind = models.CharField(max_length=20, choices=FluidKind.choices)
    # За масло на кутия - при коя кутия важи (напр. DSG). За двигателно масло - празно.
    transmission = models.CharField(max_length=20, choices=Transmission.choices, blank=True, null=True)
    viscosity = models.CharField("Вискозитет", max_length=10, blank=True, null=True)
    approvals = models.CharField("Одобрения", max_length=120)  # „VW 504.00, VW 507.00“
    capacity_litres = models.DecimalField("Количество, л", max_digits=6, decimal_places=2)

    @property
    def summary(self):
        """„5W-30, VW 507.00 · 4,3 л“ - винаги с десетична запетая."""
        litres = f"{self.capacity_litres.normalize():f}".replace(".", ",")
        viscosity = f"{self.viscosity}, " if self.viscosity else ""
        return f"{viscosity}{self.approvals} · {litres} л"


class Vehicle(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="vehicles", verbose_name="Собственик")
    make = models.CharField("Марка", max_length=50)
    model = models.CharField("Модел", max_length=50)
    year = models.IntegerField("Година на производство", validators=[MinValueValidator(1950), MaxValueValidator(2100)])
    vin = models.CharField("VIN (поле E от талона)", max_length=17, unique=True, null=True, blank=True, validators=[VIN_VALIDATOR])
    license_plate = models.CharField("Рег. номер", max_length=10, unique=True)
    mileage = models.IntegerField("Пробег (км)", default=0, validators=[MinValueValidator(0), MaxValueValidator(3_000_000)])
    fuel_type = models.CharField("Гориво (P.3)", max_length=20, choices=FuelType.choices, default=FuelType.PETROL)
    transmission = models.CharField("Скоростна кутия", max_length=20, choices=Transmission.choices, default=Transmission.UNKNOWN)

    # Данни от свидетелството за регистрация (талона) - попълват се при приемане в сервиза.
    first_registration = models.DateField("Първа регистрация (B)", null=True, blank=True)
    engine_cc = models.IntegerField("Работен обем, куб. см (P.1)", null=True, blank=True,
                                    validators=[MinValueValidator(50), MaxValueValidator(10_000)])
    power_kw = models.IntegerField("Мощност, kW (P.2)", null=True, blank=True,
                                   validators=[MinValueValidator(1), MaxValueValidator(1_500)])
    variant = models.CharField("Вариант / версия (D.2)", max_length=60, blank=True, null=True)
    color = models.CharField("Цвят (R)", max_length=30, blank=True, null=True)

    # Двигателят - определя маслото, течностите и подходящите части.
    engine_variant = models.ForeignKey(EngineVariant, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Двигател")

    @property
    def display_name(self):
        return f"{self.make} {self.model} ({self.license_plate})"

    @property
    def is_missing_registration_data(self):
        """Липсват ли данни от талона, които рецепцията трябва да попълни при приемане."""
        return (not self.vin or self.first_registration is None or self.engine_cc is None or self.power_kw is None
                or self.transmission == Transmission.UNKNOWN or self.fuel_type == FuelType.UNKNOWN)

    def __str__(self):
        return self.display_name
