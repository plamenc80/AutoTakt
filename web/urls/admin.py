"""Администрация: справки, ценоразпис, двигатели, механици, потребители."""
from django.urls import path

from web.views import admin_engines, admin_mechanics, admin_reports, admin_services, admin_users

urlpatterns = [
    path("Admin", admin_reports.index, name="admin.home"),
    path("Admin/Reports", admin_reports.index, name="admin.reports.index"),
    path("Admin/Reports/Export", admin_reports.export, name="admin.reports.export"),
    path("Admin/Services", admin_services.index, name="admin.services.index"),
    path("Admin/Services/Create", admin_services.create, name="admin.services.create"),
    path("Admin/Services/Edit/<int:id>", admin_services.edit, name="admin.services.edit"),
    path("Admin/Services/Save", admin_services.save, name="admin.services.save"),
    path("Admin/Services/Delete/<int:id>", admin_services.delete, name="admin.services.delete"),
    path("Admin/Engines", admin_engines.index, name="admin.engines.index"),
    path("Admin/Engines/Create", admin_engines.create, name="admin.engines.create"),
    path("Admin/Engines/Edit/<int:id>", admin_engines.edit, name="admin.engines.edit"),
    path("Admin/Engines/Save", admin_engines.save, name="admin.engines.save"),
    path("Admin/Engines/Delete/<int:id>", admin_engines.delete, name="admin.engines.delete"),
    path("Admin/Mechanics", admin_mechanics.index, name="admin.mechanics.index"),
    path("Admin/Mechanics/Create", admin_mechanics.create, name="admin.mechanics.create"),
    path("Admin/Mechanics/Edit/<int:id>", admin_mechanics.edit, name="admin.mechanics.edit"),
    path("Admin/Mechanics/Save", admin_mechanics.save, name="admin.mechanics.save"),
    path("Admin/Users", admin_users.index, name="admin.users.index"),
    path("Admin/Users/Create", admin_users.create, name="admin.users.create"),
    path("Admin/Users/ChangeRole/<int:id>", admin_users.change_role, name="admin.users.changerole"),
    path("Admin/Users/ToggleLock/<int:id>", admin_users.toggle_lock, name="admin.users.togglelock"),
    path("Admin/Users/ResetPassword/<int:id>", admin_users.reset_password, name="admin.users.resetpassword"),
]
