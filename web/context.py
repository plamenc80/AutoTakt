"""Данни, достъпни във всеки шаблон: сервизът, ролите и текущата страница (за активното меню)."""
from django.conf import settings

from data.models import Role


def garage(request):
    user = request.user
    roles = set(user.groups.values_list("name", flat=True)) if user.is_authenticated else set()
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match and match.url_name else ""
    full_name = (getattr(user, "full_name", "") or getattr(user, "email", "")) if user.is_authenticated else ""
    role = next((r for r in Role.ALL if r in roles), None)
    return {
        "garage": settings.GARAGE,
        "roles": roles,
        "is_admin": Role.ADMIN in roles,
        "is_front_desk": bool(roles & set(Role.FRONT_DESK)),
        "is_mechanic": Role.MECHANIC in roles,
        "is_customer": Role.CUSTOMER in roles,
        "is_staff_user": bool(roles & set(Role.STAFF)),
        # „repairorders.details“ → раздел „repairorders“, действие „details“
        "section": url_name.rsplit(".", 1)[0] if "." in url_name else url_name,
        "action": url_name.rsplit(".", 1)[-1] if url_name else "",
        "user_full_name": full_name,
        "user_first_name": full_name.split(" ")[0] if full_name else "",
        "user_initials": "".join(p[0].upper() for p in full_name.split()[:2]) if full_name else "",
        "user_role_name": Role.NAMES.get(role, ""),
    }
