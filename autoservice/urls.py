"""Адресите на приложението (/RepairOrders/Details/5, /Admin/Services и т.н.)."""
from django.urls import include, path

urlpatterns = [path("", include("web.urls"))]

handler404 = "web.views.core.not_found"
handler403 = "web.views.core.forbidden"
handler500 = "web.views.core.server_error"
