"""
Общи помощни функции за изгледите: проверка на ролята, достъп до ремонтите, четене на стойности от формите.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlencode, urlparse

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from data.models import Customer, Mechanic, Role, parse_choice
from services.common import BusinessRuleError


# ---------------------------------------------------------------------------- права
def role_required(*roles):
    """
    Достъп само за посочените роли. Без вход → към страницата за вход (с връщане обратно);
    с вход, но без право → „Достъп отказан“.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/Account/Login?{urlencode({'ReturnUrl': _return_url(request)})}")
            if roles and not request.user.groups.filter(name__in=roles).exists():
                return redirect(f"/Account/AccessDenied?{urlencode({'ReturnUrl': request.get_full_path()})}")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _return_url(request):
    """
    Къде да се върне потребителят след входа. При изтекла сесия и действие (POST - напр. „Одобри“) адресът на
    действието не се отваря с GET (405) - връщаме го на страницата, от която е изпратено.
    """
    if request.method in ("GET", "HEAD"):
        return request.get_full_path()
    referer = urlparse(request.META.get("HTTP_REFERER") or "")
    if referer.netloc == request.get_host() and referer.path.startswith("/"):
        return referer.path + (f"?{referer.query}" if referer.query else "")
    return "/"


login_required = role_required()
staff_required = role_required(*Role.STAFF)
front_desk_required = role_required(*Role.FRONT_DESK)
admin_required = role_required(Role.ADMIN)
customer_required = role_required(Role.CUSTOMER)


def has_role(user, *roles):
    return user.is_authenticated and user.groups.filter(name__in=roles).exists()


def is_front_desk(user):
    return has_role(user, *Role.FRONT_DESK)


def current_mechanic_id(user):
    """Id на механика, ако влезлият потребител е механик."""
    if not has_role(user, Role.MECHANIC):
        return None
    return Mechanic.objects.filter(user=user).values_list("id", flat=True).first()


def can_modify(user, order):
    """Рецепцията и администраторът - всичко; механикът - своите и невъзложените ремонти."""
    if is_front_desk(user):
        return True
    mechanic_id = current_mechanic_id(user)
    return mechanic_id is not None and order.mechanic_id in (None, mechanic_id)


def current_customer(user):
    return Customer.objects.prefetch_related("vehicles").filter(user=user).first() if user.is_authenticated else None


# ---------------------------------------------------------------------------- съобщения и действия
def success(request, text):
    messages.success(request, text)


def warning(request, text):
    messages.warning(request, text)


def error(request, text):
    messages.error(request, text)


def try_action(request, action, success_message=None):
    """
    Изпълнява действие от бизнес логиката. Нарушено правило → съобщение за грешка вместо страница с грешка.
    Връща (успех, резултат).
    """
    try:
        result = action()
    except BusinessRuleError as exc:
        error(request, str(exc))
        return False, None
    if success_message:
        success(request, success_message)
    return True, result


def safe_redirect(request, url, fallback):
    """Пренасочване само към адрес в същия сайт (защита от „open redirect“)."""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}) and url.startswith("/"):
        return redirect(url)
    return redirect(fallback)


# ---------------------------------------------------------------------------- стойности от формите
def get_int(data, key, default=None):
    try:
        return int(str(data.get(key, "")).strip())
    except (TypeError, ValueError):
        return default


MAX_DECIMAL = Decimal("100000000")  # по-големи стойности не се побират в колоните на базата


def get_decimal(data, key, default=None):
    """Десетично число от формата („2,5“ или „2.5“). NaN, Infinity и огромни стойности → default."""
    raw = str(data.get(key, "")).strip().replace(",", ".")
    try:
        value = Decimal(raw) if raw else default
    except InvalidOperation:
        return default
    if value is not default and (not value.is_finite() or abs(value) >= MAX_DECIMAL):
        return default
    return value


def get_date(data, key, default=None):
    raw = str(data.get(key, "")).strip()
    try:
        return date.fromisoformat(raw[:10]) if raw else default
    except ValueError:
        return default


def get_bool(data, key):
    return str(data.get(key, "")).lower() in ("true", "on", "1")


def get_choice(data, key, choices, default=None):
    return parse_choice(choices, data.get(key), default)


def get_str(data, key):
    value = data.get(key)
    return value.strip() if value and value.strip() else None


def now():
    return datetime.now()
