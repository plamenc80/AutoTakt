"""Публична част и клиентът: начална страница, записване, „Моят гараж“."""
from django.urls import path

from web.views import booking, home, mygarage

urlpatterns = [
    path("", home.index, name="home.index"),
    path("Booking", booking.index, name="booking.index"),
    path("Booking/Done", booking.done, name="booking.done"),
    path("MyGarage", mygarage.index, name="mygarage.index"),
    path("MyGarage/Tracker", mygarage.tracker, name="mygarage.tracker"),
    path("MyGarage/Decide/<int:id>", mygarage.decide, name="mygarage.decide"),
    path("MyGarage/Inspection/<int:id>", mygarage.inspection, name="mygarage.inspection"),
    path("MyGarage/PhotoFile/<int:id>", mygarage.photo_file, name="mygarage.photofile"),
    path("MyGarage/History/<int:id>", mygarage.history, name="mygarage.history"),
    path("MyGarage/Invoice/<int:id>", mygarage.invoice, name="mygarage.invoice"),
    path("MyGarage/AddVehicle", mygarage.add_vehicle, name="mygarage.addvehicle"),
    path("MyGarage/Book", mygarage.book, name="mygarage.book"),
    path("MyGarage/CancelAppointment/<int:id>", mygarage.cancel_appointment, name="mygarage.cancelappointment"),
]
