"""
Адресите на приложението. На този етап има само една страница - „Състояние на базата“:
колко записа има във всяка таблица и последните ремонти с изчислените суми.
"""
from django.db.models import Sum
from django.http import HttpResponse
from django.urls import path
from django.utils.html import escape

from data.models import (Appointment, CarMake, CarModel, Customer, EngineVariant, InspectionTemplate, Mechanic, Part,
                         Payment, RepairOrder, Service, User, Vehicle)

TABLES = [
    ("Потребители", User), ("Клиенти", Customer), ("Механици", Mechanic), ("Автомобили", Vehicle),
    ("Марки", CarMake), ("Модели", CarModel), ("Двигатели", EngineVariant), ("Услуги", Service),
    ("Части в склада", Part), ("Записани часове", Appointment), ("Ремонти", RepairOrder), ("Плащания", Payment),
    ("Шаблони за проверка", InspectionTemplate),
]


def euro(value):
    return f"{value or 0:,.2f} €".replace(",", " ").replace(".", ",")


def database_status(request):
    counts = "".join(f"<tr><td>{name}</td><td>{model.objects.count()}</td></tr>" for name, model in TABLES)
    orders = RepairOrder.objects.select_related("vehicle", "mechanic").order_by("-opened_on")[:10]
    rows = "".join(
        f"<tr><td>{o.id}</td><td>{o.opened_on:%d.%m.%Y}</td><td>{escape(o.vehicle.license_plate)}</td>"
        f"<td>{escape(o.get_status_display())}</td><td>{euro(o.total_labor)}</td><td>{euro(o.total_parts)}</td>"
        f"<td>{euro(o.vat)}</td><td>{euro(o.total_amount)}</td></tr>" for o in orders)
    revenue = Payment.objects.aggregate(total=Sum("amount"))["total"]
    return HttpResponse(f"""<!doctype html><html lang="bg"><meta charset="utf-8"><title>АвтоТакт - база данни</title>
<style>body{{font-family:sans-serif;margin:2rem;max-width:60rem}}table{{border-collapse:collapse;margin-bottom:2rem}}
td,th{{border:1px solid #ccc;padding:.3rem .7rem;text-align:left}}th{{background:#f2f2f2}}</style>
<h1>АвтоТакт - състояние на базата</h1>
<table><tr><th>Таблица</th><th>Записи</th></tr>{counts}</table>
<p>Общо платено: <b>{euro(revenue)}</b></p>
<h2>Последни 10 ремонта</h2>
<table><tr><th>№</th><th>Дата</th><th>Рег. номер</th><th>Статус</th><th>Труд</th><th>Части</th><th>ДДС 20%</th>
<th>Общо</th></tr>{rows}</table></html>""")


urlpatterns = [path("", database_status)]
