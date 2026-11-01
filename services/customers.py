"""Клиенти и свързването на онлайн профил с клиент от картотеката."""
from dataclasses import asdict, dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Prefetch, Q

from data.models import Appointment, AppointmentStatus, Customer, RepairOrder, User, Vehicle

from .common import BusinessRuleError, paginate, phone_key
from .plates import normalize_plate

# Записване от гост, което рецепцията проверява, защото номерът е на друг клиент (вж. appointments.book_guest).
REVIEW_NOTE = "Регистрационният номер е записан на друг клиент - проверете по телефона."


def search(term, page):
    """
    По име, телефон, имейл или рег. номер. Телефонът се сравнява по цифрите (0899456123, +359 899 456 123 и
    „0899 456 123“ са един номер), а номерът може да е и на латиница - както при „Днес“ и автомобилите.
    """
    query = Customer.objects.prefetch_related("vehicles")
    if term and term.strip():
        t = term.strip()
        condition = (Q(full_name__icontains=t) | Q(phone__icontains=t) | Q(email__icontains=t)
                     | Q(vehicles__license_plate__icontains=t) | Q(vehicles__license_plate__icontains=normalize_plate(t)))
        digits = phone_key(t)
        if len(digits) >= 3 and not any(ch.isalpha() for ch in t):
            condition |= Q(id__in=[c.id for c in Customer.objects.only("id", "phone") if digits in phone_key(c.phone)])
        query = query.filter(condition).distinct()
    return paginate(query.order_by("full_name"), page, search=term)


def get(customer_id):
    return (Customer.objects
            .prefetch_related("vehicles",
                              Prefetch("appointments", Appointment.objects.select_related("vehicle").order_by("-scheduled_for")))
            .filter(id=customer_id).first())


def for_user(user):
    return Customer.objects.prefetch_related("vehicles").filter(user=user).first() if user.is_authenticated else None


def all_customers():
    return list(Customer.objects.order_by("full_name"))


def create(full_name, phone, email=None, address=None):
    return Customer.objects.create(full_name=full_name.strip(), phone=phone.strip(), email=email or None,
                                   address=address or None, created_on=datetime.now())


@transaction.atomic
def update(customer_id, full_name, phone, email=None, address=None):
    """
    Данните на клиента. Ако клиентът има онлайн профил, имейлът е и името му за вход - сменя се и там
    (иначе картата показва имейл, с който клиентът не може да влезе).
    """
    customer = Customer.objects.select_related("user").filter(id=customer_id).first()
    if customer is None:
        raise BusinessRuleError("Клиентът не е намерен.")
    email = (email or "").strip() or None
    user = customer.user
    if user is not None and (email or "").lower() != user.email.lower():
        if email is None:
            raise BusinessRuleError("Клиентът има онлайн профил - имейлът е и името му за вход и не може да е празен.")
        if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
            raise BusinessRuleError(f"Имейлът „{email}“ вече се използва от друг профил.")
        user.email = email.lower()
        user.save(update_fields=["email"])
    customer.full_name, customer.phone, customer.email, customer.address = full_name.strip(), phone.strip(), email, address or None
    customer.save()


def find_unlinked(phone, email):
    """Клиент без профил със същия имейл и телефон - за свързване при регистрация."""
    candidates = Customer.objects.filter(user__isnull=True, email__iexact=(email or "").strip())
    return next((c for c in candidates if phone_key(c.phone) == phone_key(phone)), None)


def find_unlinked_by_email(email):
    """Единственият клиент без профил с този имейл (за профил, създаден от администратора) или None."""
    candidates = list(Customer.objects.filter(user__isnull=True, email__iexact=(email or "").strip())[:2])
    return candidates[0] if len(candidates) == 1 else None


def has_repairs(customer):
    return RepairOrder.objects.filter(Q(customer_id=customer.id) | Q(vehicle__customer_id=customer.id)).exists()


def proves_identity(customer, phone, email=None, owns_plate=False):
    """
    Може ли човек, който знае тези данни, да поеме клиента (без профил) - без SMS или потвърждение по имейл:
    - телефонът и имейлът съвпадат със записаните; или
    - телефонът съвпада и знае рег. номер на негов автомобил - само ако при клиента няма имейл (няма с какво
      друго да се сравни) и няма ремонти (няма лична история, която да се разкрие на непознат).
    Гост не може да добави автомобил към чужд клиент (вж. appointments.book_guest), затова номерът е доказателство.
    """
    if customer is None or customer.user_id is not None or phone_key(customer.phone) != phone_key(phone):
        return False
    if customer.email and email and customer.email.strip().lower() == email.strip().lower():
        return True
    return owns_plate and not customer.email and not has_repairs(customer)


def merge(source, target):
    """
    Два записа за един и същ човек (напр. гост и клиент от картотеката): автомобилите (с ремонтите им) и часовете
    минават към target, липсващите данни се допълват, source се изтрива. target се записва от извикващия.
    """
    Vehicle.objects.filter(customer=source).update(customer=target)
    Appointment.objects.filter(customer=source).update(customer=target)
    RepairOrder.objects.filter(customer=source).update(customer=target)
    target.email = target.email or source.email
    target.address = target.address or source.address
    source.delete()


def _resolve_plate_reviews(customer):
    """Часът беше „За проверка“, защото номерът е на друг клиент - вече е на същия, проверката отпада."""
    Appointment.objects.filter(customer=customer, vehicle__customer=customer, needs_review=True,
                               review_note=REVIEW_NOTE, status=AppointmentStatus.PENDING) \
        .update(needs_review=False, review_note=None)


# ---------------------------------------------------------------------------- регистрация след записване като гост
CLAIM_HOURS = 24  # „Създай профил“ след записване важи до денонощие


@dataclass
class GuestClaim:
    """
    Гост, записал час от този браузър, когото профилът може да поеме при регистрация. Пази се в сесията
    (бисквитката важи 2 седмици), затова се поема само от същия човек - същия телефон или имейл - и до CLAIM_HOURS.
    """
    customer_id: int
    phone: str      # phone_key от записването
    email: str      # имейлът от записването (малки букви) или ""
    created: float  # кога е записан часът (timestamp)

    @classmethod
    def new(cls, customer_id, phone, email):
        return cls(customer_id, phone_key(phone), (email or "").strip().lower(), datetime.now().timestamp())

    @classmethod
    def from_session(cls, data):
        try:
            return cls(**data)
        except TypeError:  # стар формат (само номер на клиента) или повредени данни
            return None

    def to_session(self):
        return asdict(self)

    def belongs_to(self, phone, email):
        fresh = datetime.now().timestamp() - self.created <= CLAIM_HOURS * 3600
        same_person = phone_key(phone) == self.phone or (self.email and (email or "").strip().lower() == self.email)
        return fresh and bool(same_person)


@dataclass
class AccountLink:
    customer: Customer
    has_repairs: bool
    vehicles: int
    appointments: int


@transaction.atomic
def link_account(user, full_name, phone, email, guest=None):
    """
    Нов онлайн профил → клиент от картотеката:
    - клиент без профил със същия телефон и имейл → историята му (find_unlinked);
    - гост, записал час в този браузър (guest - GuestClaim от сесията, ако е същият човек) → поема го с
      автомобила и часа; ако има и история - гостът се слива с нея;
    - иначе - нов клиент.
    """
    history = find_unlinked(phone, email)
    claimed = None
    if guest is not None and guest.belongs_to(phone, email):
        claimed = Customer.objects.filter(id=guest.customer_id, user__isnull=True).first()
    if history and claimed and claimed.id != history.id:
        merge(claimed, history)
        claimed = None
    customer = history or claimed
    if customer is None:
        customer = create(full_name, phone, email)
    elif history is None:  # поетият гост приема данните от регистрацията
        customer.full_name, customer.phone, customer.email = full_name.strip(), phone.strip(), email
    customer.user = user
    customer.save()
    _resolve_plate_reviews(customer)
    return AccountLink(customer, has_repairs(customer), customer.vehicles.count(), customer.appointments.count())


@transaction.atomic
def claim_guest_on_login(user, guest):
    """
    Вход в съществуващ профил веднага след записване като гост (от същия браузър, напр. имейлът вече има профил):
    гостът се слива с клиента на профила - автомобилът и часът се появяват в „Моят гараж“. Само ако е същият
    човек (телефонът на клиента или имейлът на профила са дадени при записването) - друг човек, влязъл в същия
    браузър, не поема чуждия час. Връща AccountLink или None.
    """
    customer = Customer.objects.filter(user=user).first()
    if guest is None or customer is None or not guest.belongs_to(customer.phone, user.email):
        return None
    claimed = Customer.objects.filter(id=guest.customer_id, user__isnull=True).exclude(id=customer.id).first()
    if claimed is None:
        return None
    merge(claimed, customer)
    customer.save()
    _resolve_plate_reviews(customer)
    return AccountLink(customer, has_repairs(customer), customer.vehicles.count(), customer.appointments.count())


@transaction.atomic
def claim_vehicle(customer, plate):
    """
    „Добави автомобил“ с номер, който вече е записан на клиент без профил със същия телефон (напр. гост, записал
    час без имейл, после регистриран от друго устройство): ако proves_identity - двата записа се сливат в профила.
    Връща True при сливане.
    """
    vehicle = Vehicle.objects.select_related("customer").filter(license_plate=normalize_plate(plate)).first()
    if vehicle is None or vehicle.customer_id == customer.id:
        return False
    if not proves_identity(vehicle.customer, customer.phone, customer.email, owns_plate=True):
        return False
    merge(vehicle.customer, customer)
    customer.save()
    _resolve_plate_reviews(customer)
    return True


def link_user(customer_id, user):
    customer = Customer.objects.filter(id=customer_id).first()
    if customer is None:
        raise BusinessRuleError("Клиентът не е намерен.")
    customer.user = user
    customer.save()


def delete(customer_id):
    customer = Customer.objects.filter(id=customer_id).first()
    if customer is None:
        raise BusinessRuleError("Клиентът не е намерен.")
    if customer.vehicles.exists():
        raise BusinessRuleError("Клиентът има регистрирани автомобили и не може да бъде изтрит.")
    if customer.repair_orders.exists():  # напр. продал е колата - протоколите му остават
        raise BusinessRuleError("Клиентът има ремонти в историята и не може да бъде изтрит.")
    customer.appointments.all().delete()
    customer.delete()
