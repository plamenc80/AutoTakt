"""Общи адреси: начало, грешки, вход/регистрация, справочни API и сигнал за промени."""
from django.urls import path

from web.views import core

urlpatterns = [
    path("Home/StatusCode", core.status_code, name="home.statuscode"),
    path("Home/Error", core.error_page, name="home.error"),

    path("Account/Login", core.login_view, name="account.login"),
    path("Account/Register", core.register, name="account.register"),
    path("Account/Logout", core.logout_view, name="account.logout"),
    path("Account/AccessDenied", core.access_denied, name="account.accessdenied"),

    path("api/makes", core.api_makes, name="api.makes"),
    path("api/models", core.api_models, name="api.models"),
    path("api/vin", core.api_vin, name="api.vin"),
    path("api/plate", core.api_plate, name="api.plate"),
    path("api/slots", core.api_slots, name="api.slots"),
    path("api/customers/<int:customer_id>/vehicles", core.api_customer_vehicles, name="api.customervehicles"),
    path("api/changes", core.api_changes, name="api.changes"),
]
