"""
Демо данни: роли и демо акаунти, ценоразпис, склад, двигатели, 20 клиента, 30 автомобила,
300 ремонта за последната година (за справките), текущи ремонти, часове и записване от гост за проверка.

Генераторът на случайни числа е с фиксирано начало - при всяко създаване данните са едни и същи.
Данните, на които разчитат демото и тестовете (Kia Ceed „СН 7990 ХТ“ на Иван Димитров, ремонт № 303),
са зададени изрично.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

from django.contrib.auth.models import Group
from django.db import transaction

from data.models import (VAT_RATE, Appointment, AppointmentStatus, CarMake, CarModel, Customer, EngineVariant,
                         FluidRequirement, FuelType, Inspection, InspectionRating, InspectionResult, Mechanic, Part,
                         PartFitment, PartUnit, Payment, PaymentMethod, Recommendation, RepairOrder,
                         RepairOrderPartLine, RepairOrderServiceLine, RepairStatus, Role, Service, ServiceCategory,
                         ServicePackageItem, Transmission, User, Vehicle, round_money)

from .car_catalog import MAKES
from .engine_catalog import ENGINES, FLUID_PARTS
from .inspection_templates import create_templates


def _today_at(day, hour, minute=0):
    return datetime.combine(day, time()) + timedelta(hours=hour, minutes=minute)


def _next_working_day(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


class Seeder:
    def __init__(self):
        self.rng = random.Random(2026)   # основният генератор
        self.extra = random.Random(77)   # отделен за данните от талона
        self.today = date.today()

    # ------------------------------------------------------------------ вход
    @transaction.atomic
    def run(self):
        for role in Role.ALL:
            Group.objects.get_or_create(name=role)

        if not CarMake.objects.exists():
            for make, models in MAKES:
                car_make = CarMake.objects.create(name=make)
                CarModel.objects.bulk_create([CarModel(make=car_make, name=m) for m in models])

        if Customer.objects.exists():
            return False  # базата вече е попълнена

        self.create_users()
        self.mechanics = [
            Mechanic.objects.create(full_name="Георги Петров", specialty="Двигатели и диагностика", hourly_rate=30, user=self.mechanic_user),
            Mechanic.objects.create(full_name="Николай Стоянов", specialty="Ходова част и спирачки", hourly_rate=25),
            Mechanic.objects.create(full_name="Димитър Колев", specialty="Автоелектрика", hourly_rate=28),
        ]
        self.services = self.create_services()
        self.parts = self.create_parts()
        self.engines = self.create_engines()
        self.add_fitments()
        self.customers = self.create_customers()
        self.vehicles = self.create_vehicles()
        self.assign_engines()
        for vehicle in self.vehicles:
            vehicle.save()

        busy = self.create_repair_history()
        busy.add(self.vehicles[0].id)
        templates = create_templates(self.services)
        self.create_demo_client_repair(templates[0])
        self.create_appointments(busy)
        free = next(v for v in self.vehicles[1:] if v.id not in busy)
        self.create_guest_booking_for_review(free)
        return True

    # ------------------------------------------------------------------ потребители
    def create_user(self, email, password, full_name, role):
        user = User.objects.create_user(email=email, password=password, full_name=full_name)
        user.groups.add(Group.objects.get(name=role))
        return user

    def create_users(self):
        self.create_user("admin@avtotakt.com", "Admin123!", "Администратор", Role.ADMIN)
        self.create_user("reception@avtotakt.com", "Reception123!", "Мария Иванова", Role.RECEPTIONIST)
        self.mechanic_user = self.create_user("mechanic@avtotakt.com", "Mechanic123!", "Георги Петров", Role.MECHANIC)
        self.client_user = self.create_user("client@avtotakt.com", "Client123!", "Иван Димитров", Role.CUSTOMER)

    # ------------------------------------------------------------------ ценоразпис
    def create_services(self):
        rows = [
            ("Смяна на двигателно масло и филтър", 25, "0.5"), ("Компютърна диагностика", 35, "0.5"),
            ("Смяна на предни накладки", 40, "1"), ("Смяна на задни накладки", 45, "1"),
            ("Смяна на спирачни дискове (к-т)", 60, "1.5"), ("Смяна на ангренажен ремък", 180, "4"),
            ("Смяна на съединител", 250, "5"), ("Геометрия на колелата", 40, "1"),
            ("Смяна на гуми (4 бр.) и баланс", 30, "0.75"), ("Зареждане на климатик", 50, "0.75"),
            ("Смяна на акумулатор", 15, "0.25"), ("Смяна на амортисьори (2 бр.)", 90, "2"),
            ("Смяна на свещи", 30, "0.5"), ("Годишен технически преглед - подготовка", 20, "0.5"),
        ]
        # Интервали за „здравето“: индекс → (км, месеца)
        intervals = {0: (15000, 12), 2: (40000, 36), 3: (60000, 48), 4: (80000, 60), 5: (90000, 60),
                     9: (None, 24), 10: (None, 60), 11: (80000, None), 12: (40000, 36), 13: (None, 12)}
        C = ServiceCategory
        categories = [C.MAINTENANCE, C.ELECTRICAL, C.BRAKES, C.BRAKES, C.BRAKES, C.ENGINE, C.ENGINE, C.SUSPENSION,
                      C.TYRES, C.AIR_CONDITIONING, C.ELECTRICAL, C.SUSPENSION, C.ENGINE, C.MAINTENANCE]
        featured = {0: "oil", 2: "brakes", 9: "ac", 8: "tyres", 1: "diagnostics", 4: "discs"}

        services = []
        for i, (name, price, hours) in enumerate(rows):
            km, months = intervals.get(i, (None, None))
            services.append(Service.objects.create(
                name=name, price=D(price), estimated_hours=D(hours), interval_km=km, interval_months=months,
                category=categories[i], sort_order=i * 10, is_featured=i in featured,
                image_url=f"/img/services/{featured[i]}.jpg" if i in featured else None))

        # Пакети: обща цена, по-ниска от сбора на включените услуги.
        small = Service.objects.create(
            name="Малко обслужване", price=D(50), estimated_hours=D(1), is_package=True, sort_order=1,
            description="Смяна на масло и маслен филтър и компютърна диагностика - за редовната годишна поддръжка.")
        big = Service.objects.create(
            name="Голямо обслужване", price=D(150), estimated_hours=D("3.5"), is_package=True, sort_order=2,
            badge="Най-избирано",
            description="Масло и филтър, диагностика, свещи, зареждане на климатик и геометрия - всичко преди дълъг път.")
        for index in (0, 1):
            ServicePackageItem.objects.create(package=small, service=services[index])
        for index in (0, 1, 12, 9, 7):
            ServicePackageItem.objects.create(package=big, service=services[index])
        return services + [small, big]

    # ------------------------------------------------------------------ склад
    def create_parts(self):
        rows = [
            dict(name="Масло 5W-30 LongLife (VW)", part_number="OIL-5W30-LL", unit_price=D("11.5"), quantity_in_stock=160,
                 min_stock_level=20, unit=PartUnit.LITRE, fluid_kind="EngineOil", viscosity="5W-30",
                 approvals="VW 504.00, VW 507.00, ACEA C3"),
            dict(name="Маслен филтър", part_number="MANN-W712", manufacturer="MANN-FILTER", unit_price=D("9.5"), quantity_in_stock=35, min_stock_level=10),
            dict(name="Въздушен филтър", part_number="MANN-C27009", manufacturer="MANN-FILTER", unit_price=D(14), quantity_in_stock=20, min_stock_level=5),
            dict(name="Филтър купе", part_number="BOSCH-1987432", manufacturer="Bosch", unit_price=D(12), quantity_in_stock=18, min_stock_level=5),
            dict(name="Предни накладки (к-т)", part_number="BREMBO-P85020", manufacturer="Brembo", unit_price=D(42), quantity_in_stock=12, min_stock_level=4),
            dict(name="Задни накладки (к-т)", part_number="BREMBO-P85073", manufacturer="Brembo", unit_price=D(36), quantity_in_stock=3, min_stock_level=4),
            dict(name="Спирачен диск преден", part_number="ATE-24012501", manufacturer="ATE", unit_price=D(38), quantity_in_stock=16, min_stock_level=4),
            dict(name="Ангренажен к-т с водна помпа", part_number="GATES-KP15578", manufacturer="Gates", unit_price=D(165), quantity_in_stock=4, min_stock_level=2),
            dict(name="Съединител к-т", part_number="LUK-624318", manufacturer="LuK", unit_price=D(210), quantity_in_stock=2, min_stock_level=1),
            dict(name="Акумулатор 74Ah", part_number="VARTA-E11", manufacturer="Varta", unit_price=D(120), quantity_in_stock=6, min_stock_level=2),
            dict(name="Амортисьор преден", part_number="SACHS-313478", manufacturer="Sachs", unit_price=D(68), quantity_in_stock=8, min_stock_level=2),
            dict(name="Запалителна свещ", part_number="NGK-BKR6E", manufacturer="NGK", unit_price=D("7.5"), quantity_in_stock=48, min_stock_level=16),
            dict(name="Хладилна течност (5 л)", part_number="MOTUL-COOL5", manufacturer="Motul", unit_price=D(22), quantity_in_stock=1, min_stock_level=3, is_universal=True),
            dict(name="Чистачки (к-т)", part_number="BOSCH-A863S", manufacturer="Bosch", unit_price=D(28), quantity_in_stock=10, min_stock_level=3),
        ]
        # индекси 14+ - течностите не променят историята
        return [Part.objects.create(**row) for row in rows + FLUID_PARTS]

    def create_engines(self):
        engines = []
        for makes, name, code, fuel, cc, kw, fluids in ENGINES:
            engine = EngineVariant.objects.create(makes=makes, name=name, engine_code=code, fuel_type=fuel,
                                                  displacement_cc=cc, power_kw=kw)
            for fluid in fluids:
                FluidRequirement.objects.create(engine_variant=engine, **fluid)
            engines.append(engine)
        return engines

    def add_fitments(self):
        """Филтри и накладки, подходящи за определени двигатели (за „Подходящи“ при влагане)."""
        def fit(part_number, which):
            part = next(p for p in self.parts if p.part_number == part_number)
            for engine in filter(which, self.engines):
                PartFitment.objects.create(part=part, engine_variant=engine)

        fit("OF-VAG-TDI", lambda e: e.applies_to("Skoda") and e.fuel_type == FuelType.DIESEL)
        fit("MANN-W712", lambda e: e.applies_to("Skoda") and e.fuel_type == FuelType.PETROL)
        fit("OF-HK-16", lambda e: e.applies_to("Kia"))
        fit("BREMBO-P85020", lambda e: e.applies_to("Kia") or e.applies_to("Skoda"))
        fit("ATE-24012501", lambda e: e.applies_to("Kia") or e.applies_to("Skoda"))

    # ------------------------------------------------------------------ клиенти и автомобили
    def create_customers(self):
        names = [
            "Иван Димитров", "Петър Георгиев", "Елена Николова", "Стефан Тодоров", "Мартин Христов",
            "Десислава Петрова", "Александър Илиев", "Христо Атанасов", "Виктория Стоянова", "Борис Михайлов",
            "Калоян Василев", "Радослав Ангелов", "Ния Костадинова", "Тодор Йорданов", "Светослав Маринов",
            "Габриела Попова", "Красимир Димов", "Йоана Станчева", "Любомир Павлов", "Цветелина Русева",
        ]
        streets = ["ул. Витоша", "бул. Шипка", "ул. Раковски", "бул. България", "ул. Хан Аспарух", "ул. Цар Освободител"]
        customers = []
        for i, name in enumerate(names):
            customers.append(Customer.objects.create(
                full_name=name,
                phone=f"08{self.rng.randrange(7, 10)}{self.rng.randrange(1000000, 9999999)}",
                email=None if i % 3 == 2 else f"client{i + 1}@mail.bg",
                address=f"гр. София, {streets[i % len(streets)]} {self.rng.randrange(1, 120)}",
                created_on=_today_at(self.today - timedelta(days=self.rng.randrange(380, 900)), 0)))
        customers[0].user = self.client_user
        customers[0].email = self.client_user.email
        customers[0].save()
        return customers

    def random_vin(self):
        allowed = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        return "".join(self.rng.choice(allowed) for _ in range(17))

    def create_vehicles(self):
        models = [("VW", "Golf"), ("VW", "Passat"), ("Opel", "Astra"), ("Toyota", "Corolla"), ("Toyota", "Yaris"),
                  ("BMW", "320d"), ("Audi", "A4"), ("Skoda", "Octavia"), ("Renault", "Clio"), ("Ford", "Focus"),
                  ("Mercedes-Benz", "C 220"), ("Peugeot", "308"), ("Dacia", "Duster"), ("Hyundai", "i30"), ("Kia", "Ceed")]
        # Предимно софийски номера (С, СА, СВ, СО). Списъкът е все така от 8 елемента - случайните данни не се променят.
        regions = ["СА", "СА", "СВ", "С", "СА", "СО", "СН", "РВ"]
        letters = "АВЕКМНОРСТУХ"
        fuels = [FuelType.PETROL, FuelType.DIESEL, FuelType.LPG, FuelType.HYBRID]
        used_vins, used_plates = set(), {"СН 7990 ХТ"}
        vehicles = []
        for i in range(30):
            # Първите 20 клиента имат по един автомобил, а някои - по два.
            owner = self.customers[i] if i < len(self.customers) else self.rng.choice(self.customers)
            make, model = models[self.rng.randrange(len(models))]
            year = self.rng.randrange(2006, 2025)
            vin = self.random_vin()
            while vin in used_vins:
                vin = self.random_vin()
            used_vins.add(vin)
            plate = None
            while plate is None or plate in used_plates:
                plate = (f"{self.rng.choice(regions)} {self.rng.randrange(1000, 9999)} "
                         f"{self.rng.choice(letters)}{self.rng.choice(letters)}")
            used_plates.add(plate)
            mileage = (2026 - year) * self.rng.randrange(12000, 22000)
            fuel = fuels[self.rng.randrange(4)]
            if i == 0:
                # Автомобилът на демо клиента - на него разчитат демото и тестовете.
                make, model, year, plate, mileage, fuel = "Kia", "Ceed", 2017, "СН 7990 ХТ", 154_341, FuelType.DIESEL
            vehicle = Vehicle(customer=owner, make=make, model=model, year=year, vin=vin, license_plate=plate,
                              mileage=mileage, fuel_type=fuel)
            self.fill_registration_data(vehicle, i)
            vehicles.append(vehicle)
        return vehicles

    def fill_registration_data(self, vehicle, index):
        """Данни от талона. Всеки четвърти автомобил остава непълен - за картата „Данни от талона“."""
        vehicle.transmission = Transmission.AUTOMATIC if self.extra.randrange(4) == 0 else Transmission.MANUAL
        vehicle.color = ["Сив", "Черен", "Бял", "Син", "Червен", "Сребрист"][self.extra.randrange(6)]
        if index % 4 == 3 and index != 0:
            return
        vehicle.first_registration = date(vehicle.year, self.extra.randrange(1, 13), self.extra.randrange(1, 28))
        options = ([(1598, 77), (1968, 110), (1461, 66), (1995, 120)] if vehicle.fuel_type == FuelType.DIESEL
                   else [(1395, 92), (1598, 85), (999, 70), (1798, 103)])
        vehicle.engine_cc, vehicle.power_kw = options[self.extra.randrange(4)]

    def assign_engines(self):
        """Двигател по марка и гориво; колите с непълни данни остават без двигател (избира се при приемане)."""
        for i, vehicle in enumerate(self.vehicles):
            if vehicle.engine_cc is None and i != 0:
                continue
            candidates = [e for e in self.engines if e.applies_to(vehicle.make)]
            engine = next((e for e in candidates if e.fuel_type == vehicle.fuel_type), None)
            if engine is None and i == 0 and candidates:
                engine = candidates[0]  # демо клиентът винаги има двигател
            if engine is None:
                continue
            vehicle.engine_variant = engine
            vehicle.fuel_type = engine.fuel_type
            vehicle.engine_cc = engine.displacement_cc
            vehicle.power_kw = engine.power_kw
            vehicle.variant = vehicle.variant or engine.name

    # ------------------------------------------------------------------ ремонти
    @staticmethod
    def save_order(order, service_lines, part_lines, payments=()):
        """Записва ремонта с редовете му и изчислява сумите (труд + части + 20% ДДС)."""
        order.total_labor = sum((round_money(l.quantity * l.price_at_time) for l in service_lines), D(0))
        order.total_parts = sum((round_money(l.quantity * l.unit_price_at_time) for l in part_lines), D(0))
        order.vat = round_money((order.total_labor + order.total_parts) * VAT_RATE)
        order.total_amount = order.total_labor + order.total_parts + order.vat
        order.save()
        for line in list(service_lines) + list(part_lines) + list(payments):
            line.repair_order = order
            line.save()
        return order

    def create_repair_history(self):
        """300 ремонта за последните 12 месеца, за да има данни за справките. Връща колите с текущ ремонт."""
        parts_for_service = {0: [(0, 4), (1, 1)], 2: [(4, 1)], 3: [(5, 1)], 4: [(6, 2), (4, 1)], 5: [(7, 1), (12, 1)],
                             6: [(8, 1)], 10: [(9, 1)], 11: [(10, 2)], 12: [(11, 4)]}
        singles = self.services[:14]
        count = 300
        drafts = []
        for i in range(count):
            days_ago = int(365.0 * (count - i) / count)  # равномерно през годината
            opened = _today_at(self.today - timedelta(days=days_ago), self.rng.randrange(8, 17))
            vehicle = self.vehicles[self.rng.randrange(len(self.vehicles))]
            order = RepairOrder(vehicle=vehicle, mechanic=self.rng.choice(self.mechanics), opened_on=opened,
                                mileage_at_service=max(0, vehicle.mileage - days_ago * self.rng.randrange(20, 50)),
                                status=RepairStatus.PAID, closed_on=opened + timedelta(hours=self.rng.randrange(2, 30)))
            indexes = sorted(range(len(singles)), key=lambda _: self.rng.random())[:self.rng.randrange(1, 4)]
            lines, part_lines = [], []
            for si in indexes:
                lines.append(RepairOrderServiceLine(service=singles[si], quantity=1, price_at_time=singles[si].price,
                                                    is_done=True, done_on=order.closed_on))
                for part_index, quantity in parts_for_service.get(si, []):
                    part = self.parts[part_index]
                    part_lines.append(RepairOrderPartLine(part=part, quantity=D(quantity), unit_price_at_time=part.unit_price))
            drafts.append([order, lines, part_lines, []])

        # Текущите (неплатени) ремонти са сред последните, разпръснати между платените.
        current = [(1, RepairStatus.OPEN), (2, RepairStatus.OPEN), (4, RepairStatus.IN_PROGRESS),
                   (6, RepairStatus.IN_PROGRESS), (9, RepairStatus.DONE), (12, RepairStatus.DONE)]
        busy = set()
        for from_end, status in current:
            order, lines, _, _ = drafts[-from_end]
            order.status = status
            # Една кола не може да има два текущи ремонта - при повторение се взима друга (не на демо клиента).
            if order.vehicle.id in busy or order.vehicle is self.vehicles[0]:
                order.vehicle = next(v for v in self.vehicles[1:] if v.id not in busy)
                order.mileage_at_service = max(0, order.vehicle.mileage - self.rng.randrange(50, 400))
            busy.add(order.vehicle.id)
            if status in (RepairStatus.OPEN, RepairStatus.IN_PROGRESS):
                for line in lines:
                    line.is_done, line.done_on = False, None
                if status == RepairStatus.IN_PROGRESS:
                    lines[0].is_done, lines[0].done_on = True, order.opened_on + timedelta(hours=2)
            if status != RepairStatus.DONE:
                order.closed_on = None
                order.mechanic = self.mechanics[0]  # текущите ремонти са на демо механика

        methods = [PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]
        for draft in drafts:
            order, lines, part_lines, payments = draft
            self.save_order(order, lines, part_lines)  # сумите са нужни за плащането
            if order.status == RepairStatus.PAID:
                Payment.objects.create(repair_order=order, amount=order.total_amount,
                                       method=methods[self.rng.randrange(3)], paid_on=order.closed_on or order.opened_on)
        # Частично плащане (капаро) по един завършен ремонт.
        partial = drafts[-12][0]
        Payment.objects.create(repair_order=partial, amount=round_money(partial.total_amount / 2),
                               method=PaymentMethod.CASH, paid_on=partial.closed_on or partial.opened_on)
        return busy

    def create_demo_client_repair(self, template):
        """
        Автомобилът на демо клиента: смяна на масло преди ~11 месеца (наближава), годишен преглед преди
        повече от година (просрочен) и текущ ремонт (№ 303) със завършена проверка и препоръка за дисковете.
        """
        vehicle, mechanic, s, p = self.vehicles[0], self.mechanics[0], self.services, self.parts

        past = _today_at(self.today, 10) - _months(11) - timedelta(days=5)
        past_order = RepairOrder(vehicle=vehicle, mechanic=mechanic, opened_on=past, closed_on=past + timedelta(hours=3),
                                 mileage_at_service=vehicle.mileage - 13800, status=RepairStatus.PAID)
        self.save_order(past_order,
                        [RepairOrderServiceLine(service=s[0], quantity=1, price_at_time=s[0].price, is_done=True, done_on=past + timedelta(hours=1))],
                        [RepairOrderPartLine(part=p[0], quantity=D("4.3"), unit_price_at_time=p[0].unit_price, spec_snapshot=p[0].spec_summary),
                         RepairOrderPartLine(part=p[1], quantity=D(1), unit_price_at_time=p[1].unit_price)])
        Payment.objects.create(repair_order=past_order, amount=past_order.total_amount, method=PaymentMethod.CARD, paid_on=past_order.closed_on)

        review = _today_at(self.today, 14) - _months(12) - timedelta(days=20)
        review_order = RepairOrder(vehicle=vehicle, mechanic=mechanic, opened_on=review, closed_on=review + timedelta(hours=1),
                                   mileage_at_service=vehicle.mileage - 15200, status=RepairStatus.PAID)
        self.save_order(review_order, [RepairOrderServiceLine(service=s[13], quantity=1, price_at_time=s[13].price,
                                                              is_done=True, done_on=review + timedelta(minutes=40))], [])
        Payment.objects.create(repair_order=review_order, amount=review_order.total_amount, method=PaymentMethod.CASH, paid_on=review_order.closed_on)

        opened = _today_at(self.today, 9)
        order = RepairOrder(vehicle=vehicle, mechanic=mechanic, opened_on=opened, mileage_at_service=vehicle.mileage,
                            status=RepairStatus.IN_PROGRESS, notes="Скърцане при спиране, вибрации във волана.")
        self.save_order(order,
                        [RepairOrderServiceLine(service=s[1], quantity=1, price_at_time=s[1].price, is_done=True, done_on=opened + timedelta(minutes=40)),
                         RepairOrderServiceLine(service=s[2], quantity=1, price_at_time=s[2].price)],
                        [RepairOrderPartLine(part=p[4], quantity=D(1), unit_price_at_time=p[4].unit_price)])

        # Завършена стандартна проверка: накладките и дисковете - червени, чистачките - жълти, останалото - наред.
        inspection = Inspection.objects.create(repair_order=order, template=template, mechanic=mechanic,
                                               started_on=opened + timedelta(minutes=10), completed_on=opened + timedelta(minutes=35))
        measurements = {"Грайфер - предна лява": D("4.6"), "Грайфер - предна дясна": D("4.4"), "Грайфер - задна лява": D("5.1"),
                        "Грайфер - задна дясна": D("5.0"), "Предни накладки": D("1.8"), "Задни накладки": D("4.2"),
                        "Акумулатор - здраве": D(78)}
        discs = None
        for item in template.items.order_by("sort_order"):
            result = InspectionResult(inspection=inspection, template_item=item, rating=InspectionRating.GREEN)
            if item.name in measurements:
                value = measurements[item.name]
                result.measurement = value
                result.rating = (InspectionRating.RED if item.fail_below is not None and value < item.fail_below
                                 else InspectionRating.YELLOW if item.warn_below is not None and value < item.warn_below
                                 else InspectionRating.GREEN)
            if item.name == "Предни дискове":
                result.rating, result.note = InspectionRating.RED, "24,1 мм при минимум 25 мм, набраздени."
            elif item.name == "Предни накладки":
                result.note = "Сменят се в този ремонт."
            elif item.name == "Чистачки":
                result.rating, result.note = InspectionRating.YELLOW, "Оставят ивици - да се сменят преди зимата."
            result.save()
            if item.name == "Предни дискове":
                discs = result

        Recommendation.objects.create(
            repair_order=order, service=s[4], quantity=1, price=s[4].price, created_on=opened + timedelta(minutes=50),
            inspection_result=discs,
            note="Предните дискове са под минималната дебелина (24,1 мм при минимум 25 мм). Препоръчваме смяна заедно с накладките.")

    # ------------------------------------------------------------------ часове
    def create_appointments(self, busy):
        free = [v for v in self.vehicles[1:] if v.id not in busy]
        problems = ["Чука при завиване", "Свети лампа за двигателя", "Смяна на масло", "Скърцат спирачките",
                    "Не работи климатикът", "Подготовка за ГТП", "Вибрации при скорост над 100 км/ч", "Трудно палене сутрин"]
        def random_service():  # понякога без услуга („не знам какво е“), понякога и пакет
            return None if self.rng.randrange(3) == 0 else self.services[self.rng.randrange(len(self.services))]

        # Днешни часове (ако днес е работен ден) - сутрешните вече са потвърдени.
        if self.today.weekday() < 5:
            for hour in (9, 11, 15):
                vehicle = free.pop(self.rng.randrange(len(free)))  # всяка кола идва само веднъж днес
                Appointment.objects.create(
                    vehicle=vehicle, customer=vehicle.customer, scheduled_for=_today_at(self.today, hour),
                    description=problems[self.rng.randrange(len(problems))], service=random_service(),
                    status=AppointmentStatus.CONFIRMED if hour < 12 else AppointmentStatus.PENDING)

        # Предстоящи часове през следващите работни дни.
        day, added = self.today, 0
        while added < 10:
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for j in range(2):
                if added >= 10:
                    break
                vehicle = free[self.rng.randrange(len(free))]
                Appointment.objects.create(
                    vehicle=vehicle, customer=vehicle.customer,
                    scheduled_for=_today_at(day, 9 + j * 3 + self.rng.randrange(0, 2)),
                    description=problems[self.rng.randrange(len(problems))], service=random_service(),
                    status=AppointmentStatus.PENDING if added % 3 == 0 else AppointmentStatus.CONFIRMED)
                added += 1

        # Демо клиентът си е записал смяна на масло след ~10 дни („здравето“ показва, че наближава).
        oil_day = _next_working_day(self.today + timedelta(days=10))
        Appointment.objects.create(vehicle=self.vehicles[0], customer=self.vehicles[0].customer,
                                   scheduled_for=_today_at(oil_day, 10), description="Смяна на масло - наближава по график",
                                   service=self.services[0], status=AppointmentStatus.CONFIRMED)

    def create_guest_booking_for_review(self, vehicle):
        """Записване от гост, чийто рег. номер е на друг клиент - рецепцията трябва да го провери."""
        day = _next_working_day(self.today + timedelta(days=1))
        guest = Customer.objects.create(full_name="Петя Колева", phone="0899 456 123", email="petya.koleva@mail.bg")
        Appointment.objects.create(
            customer=guest, vehicle=vehicle, service=self.services[0], scheduled_for=_today_at(day, 16),
            description="Смяна на масло преди дълъг път", status=AppointmentStatus.PENDING, is_guest_booking=True,
            needs_review=True, review_note="Регистрационният номер е записан на друг клиент - проверете по телефона.")


def _months(n):
    """Приблизително n месеца назад (30,44 дни) - за демо датите е достатъчно."""
    return timedelta(days=round(n * 30.44))


def seed():
    return Seeder().run()
