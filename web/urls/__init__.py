"""
Всички адреси, групирани по част на приложението. Имената са „<раздел>.<действие>“
(напр. „repairorders.details“) - в шаблоните: {% url 'repairorders.details' order.id %}.
"""
from . import admin, core, customer, frontdesk, repairs

urlpatterns = core.urlpatterns + customer.urlpatterns + frontdesk.urlpatterns + repairs.urlpatterns + admin.urlpatterns
