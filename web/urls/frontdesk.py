"""Рецепция: „Днес“, табло, клиенти, автомобили, график, склад."""
from django.urls import path

from web.views import appointments, customers, dashboard, parts, reception, vehicles

urlpatterns = [
    path("Reception", reception.index, name="reception.index"),
    path("Reception/Lookup", reception.lookup, name="reception.lookup"),
    path("Reception/Sections", reception.sections, name="reception.sections"),
    path("Reception/Confirm/<int:id>", reception.confirm, name="reception.confirm"),
    path("Reception/Cancel/<int:id>", reception.cancel, name="reception.cancel"),
    path("Reception/CheckIn/<int:id>", reception.check_in, name="reception.checkin"),
    path("Dashboard", dashboard.index, name="dashboard.index"),
    path("Customers", customers.index, name="customers.index"),
    path("Customers/Details/<int:id>", customers.details, name="customers.details"),
    path("Customers/Create", customers.create, name="customers.create"),
    path("Customers/Edit/<int:id>", customers.edit, name="customers.edit"),
    path("Customers/Delete/<int:id>", customers.delete, name="customers.delete"),
    path("Vehicles", vehicles.index, name="vehicles.index"),
    path("Vehicles/Details/<int:id>", vehicles.details, name="vehicles.details"),
    path("Vehicles/Create", vehicles.create, name="vehicles.create"),
    path("Vehicles/Edit/<int:id>", vehicles.edit, name="vehicles.edit"),
    path("Vehicles/Delete/<int:id>", vehicles.delete, name="vehicles.delete"),
    path("Vehicles/CompleteRegistration/<int:id>", vehicles.complete_registration, name="vehicles.completeregistration"),
    path("Vehicles/SetEngine/<int:id>", vehicles.set_engine, name="vehicles.setengine"),
    path("Appointments", appointments.index, name="appointments.index"),
    path("Appointments/Create", appointments.create, name="appointments.create"),
    path("Appointments/Confirm/<int:id>", appointments.confirm, name="appointments.confirm"),
    path("Appointments/Cancel/<int:id>", appointments.cancel, name="appointments.cancel"),
    path("Parts", parts.index, name="parts.index"),
    path("Parts/Create", parts.create, name="parts.create"),
    path("Parts/Edit/<int:id>", parts.edit, name="parts.edit"),
    path("Parts/Save", parts.save, name="parts.save"),
    path("Parts/Restock/<int:id>", parts.restock, name="parts.restock"),
    path("Parts/Delete/<int:id>", parts.delete, name="parts.delete"),
]
