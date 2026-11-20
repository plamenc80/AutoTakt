"""
Филтри и малки компоненти за шаблоните.
Зареждат се автоматично във всеки шаблон (settings.TEMPLATES → builtins).
Текстът в компонентите се кодира с format_html - защита от XSS.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

from data.models import AppointmentStatus, PartUnit, RepairStatus

register = template.Library()

NBSP = " "  # разделител на хилядите в bg-BG


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def bg_number(value, places=2, trim=True):
    """Число с българска десетична запетая: 15.40 → „15,4“ (trim) или „15,40“."""
    number = _decimal(value)
    text = f"{number:.{places}f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


@register.filter
def euro(value):
    """Сума в евро по българския стандарт: „1 234,50 €“."""
    number = _decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # като в сумите на ремонта
    sign = "-" if number < 0 else ""
    whole, cents = f"{abs(number):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{NBSP.join(groups)},{cents} €"


@register.filter
def with_vat(price):
    """Цена с ДДС (20%) - за ценоразписа на сайта."""
    return euro(_decimal(price) * Decimal("1.20"))


@register.filter
def bg(value, places=2):
    """Дробно число с десетична запетая: 0.5 → „0,5“, 3.50 → „3,5“."""
    return bg_number(value, int(places))


@register.filter
def thousands(value):
    """Цяло число с разделител на хилядите: 154341 → „154 341“."""
    number = int(_decimal(value))
    return f"{number:,}".replace(",", NBSP)


@register.filter
def qty(quantity, unit=PartUnit.PIECE):
    """Количество с мерна единица: „4,3 л“, „2 бр.“."""
    return f"{bg_number(quantity)} {'л' if unit == PartUnit.LITRE else 'бр.'}"


@register.filter
def docnum(value):
    """Номер на документ с водещи нули: 158 → „000158“."""
    return f"{int(value):06d}"


@register.filter
def capitalize_first(text):
    """Главна първа буква: „сряда“ → „Сряда“."""
    return text[:1].upper() + text[1:] if text else text


@register.filter
def initials(name):
    """„Георги Петров“ → „ГП“."""
    return "".join(part[0].upper() for part in (name or "").split()[:2])


@register.simple_tag
def plural(count, one, many):
    """Брой с правилна форма: 1 клиент, 5 клиента."""
    return f"{count} {one if count == 1 else many}"


@register.filter
def service_icon(name):
    """Иконка (Bootstrap Icons) според името на услугата."""
    name = (name or "").lower()
    icons = [
        ("масло", "bi-droplet-half"), ("диагностика", "bi-cpu"), ("накладки", "bi-disc"), ("дискове", "bi-disc"),
        ("ремък", "bi-gear-wide-connected"), ("съединител", "bi-gear"), ("геометрия", "bi-bullseye"),
        ("гуми", "bi-life-preserver"), ("климатик", "bi-snow"), ("акумулатор", "bi-battery-charging"),
        ("амортисьори", "bi-arrows-collapse-vertical"), ("свещи", "bi-lightning-charge"), ("преглед", "bi-clipboard-check"),
    ]
    return next((icon for keyword, icon in icons if keyword in name), "bi-wrench-adjustable")


@register.simple_tag
def plate(license_plate, large=False):
    """Регистрационен номер във вида на българска табела със синя ЕС лента."""
    css = "plate plate-lg" if large else "plate"
    return format_html('<span class="{}"><span class="plate-eu" aria-hidden="true">BG</span>'
                       '<span class="plate-num">{}</span></span>', css, license_plate or "")


@register.simple_tag
def chip(text, tone="neutral"):
    """Малък етикет с цветна точка. tone: ok, info, warn, danger, neutral."""
    return format_html('<span class="status tone-{}">{}</span>', tone, text)


_REPAIR_TONES = {RepairStatus.IN_PROGRESS: "info", RepairStatus.DONE: "warn", RepairStatus.PAID: "ok"}
_APPOINTMENT_TONES = {AppointmentStatus.PENDING: "warn", AppointmentStatus.CONFIRMED: "info",
                      AppointmentStatus.COMPLETED: "ok", AppointmentStatus.CANCELLED: "danger"}


@register.simple_tag
def status(obj):
    """Статус на ремонт или час. Цветът подсказва следващата стъпка (жълто = чака плащане)."""
    if obj.status in RepairStatus.values:
        return chip(RepairStatus(obj.status).label, _REPAIR_TONES.get(obj.status, "neutral"))
    return chip(AppointmentStatus(obj.status).label, _APPOINTMENT_TONES.get(obj.status, "neutral"))


# ---------------------------------------------------------------------------- формуляри и адреси
@register.filter
def val(form, name):
    """Стойността на поле от формата (въведената или началната)."""
    return form.value(name) if form is not None else ""


@register.filter
def err(form, name):
    """Първата грешка за полето (празно, ако няма)."""
    return form.error(name) if form is not None else ""


@register.simple_tag
def field_error(form, name):
    """<span> с грешката за полето."""
    message = form.error(name) if form is not None else ""
    return format_html('<span class="field-validation-error">{}</span>', message) if message else ""


@register.filter
def asset(path):
    """Път към снимка от ценоразписа: „/img/services/oil.jpg“ → „/static/img/services/oil.jpg“."""
    if not path:
        return ""
    if path.startswith(("http://", "https://", "/static/")):
        return path
    return "/static/" + path.lstrip("/")


@register.simple_tag(takes_context=True)
def page_url(context, page):
    """Адрес на същата страница с друг номер на страница (останалите параметри се запазват)."""
    query = context["request"].GET.copy()
    query["page"] = page
    return f"{context['request'].path}?{query.urlencode()}"


@register.filter
def selected(value, current):
    """„selected“, ако стойностите съвпадат (за <option>)."""
    return "selected" if str(value) == str(current) else ""


@register.filter
def checked(value, current):
    return "checked" if str(value) == str(current) else ""


@register.filter
def label_of(value, choices):
    """Българското име на стойност: {{ order.status|label_of:"RepairStatus" }}."""
    from data import models
    try:
        return getattr(models, choices)(value).label
    except (AttributeError, ValueError):
        return value


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None


@register.filter
def lower_first(text):
    return text[:1].lower() + text[1:] if text else text


# ---------------------------------------------------------------------------- „здраве“
_HEALTH_LABELS = {"Overdue": "Просрочено", "Soon": "Наближава", "Ok": "Наред"}
_HEALTH_TONES = {"Overdue": "danger", "Soon": "warn", "Ok": "ok"}


@register.filter
def health_label(status):
    return _HEALTH_LABELS.get(status, "Няма данни")


@register.filter
def health_tone(status):
    return _HEALTH_TONES.get(status, "neutral")


@register.filter
def health_detail(item):
    """„след 2 300 км или до март 2027“, „просрочено с 1 200 км“."""
    from django.utils.dateformat import format as date_format
    if item.status == "Unknown":
        return "Не е извършвано в нашия сервиз"
    if item.status == "Overdue":
        if item.remaining_km is not None and item.remaining_km <= 0:
            return f"просрочено с {thousands(-item.remaining_km)} км"
        return f"просрочено от {date_format(item.due_date, 'F Y').lower()}"
    parts = []
    if item.remaining_km is not None:
        parts.append(f"след {thousands(item.remaining_km)} км")
    if item.due_date:
        parts.append(f"до {date_format(item.due_date, 'F Y').lower()}")
    return " или ".join(parts)


@register.filter
def health_worst(items):
    """Най-лошият статус - за обобщението на картата на автомобила."""
    known = [i for i in items if i.status != "Unknown"]
    if any(i.status == "Overdue" for i in known):
        return "Overdue"
    if any(i.status == "Soon" for i in known):
        return "Soon"
    return "Ok" if known else "Unknown"


@register.filter
def meter_percent(item):
    return round(min(1, item.progress) * 100)


# ---------------------------------------------------------------------------- дигитална проверка
@register.filter
def rating_label(rating, scale="Standard"):
    """Текстът на оценката според скалата (стандартна или по ГТП)."""
    if rating == "Unrated":
        return "Непроверено"
    if rating == "NotApplicable":
        return "Н/П"
    if scale == "RoadworthinessDefects":
        return {"Green": "Минава", "Yellow": "Значителен", "Red": "Опасен"}.get(rating, rating)
    return {"Green": "Добре", "Yellow": "Скоро", "Red": "Спешно"}.get(rating, rating)


@register.filter
def rating_tone(rating):
    return {"Green": "ok", "Yellow": "warn", "Red": "danger"}.get(rating, "neutral")


@register.filter
def rating_css(rating):
    return (rating or "").lower()


@register.filter
def scale_legend(scale):
    if scale == "RoadworthinessDefects":
        return "Минава - без дефект или незначителен · Значителен - няма да мине ГТП · Опасен - не бива да се движи"
    return "Добре · Скоро - да се планира · Спешно - да се смени сега"


@register.filter
def rating_count(inspection, rating):
    return inspection.count(rating)


@register.filter
def measurement_text(result):
    """„1,8 мм“ - винаги с десетична запетая."""
    if result.measurement is None:
        return ""
    return f"{bg_number(result.measurement)} {result.template_item.unit or ''}".strip()


@register.filter
def fname(form, name):
    """Името на полето в HTML (с префикс): „Form.Car.Make“."""
    return form.add_prefix(name)


@register.filter
def fid(form, name):
    """id на полето в HTML: „Form_Car_Make“ (JavaScript-ът го ползва)."""
    return form.add_prefix(name).replace(".", "_")
