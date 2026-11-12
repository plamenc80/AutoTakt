# Слой „Уеб“ - правила

Изглед → модул в `web/views/`, шаблон → `web/templates/<раздел>/`, частичен шаблон → `templates/.../_partial.html`,
заглавие на страницата → `title` в контекста.

## Адреси
- Всички адреси са в `web/urls/*.py` (`/RepairOrders/Details/5`, `/Admin/Users`).
- Име на адрес: `<раздел>.<действие>` → `{% url 'repairorders.details' order.id %}`.
- Параметрите извън пътя са в `request.GET` / `request.POST` (`lineId`, `done`, `returnTo`).

## Изгледи
- Само „тънки“: взимат данните от формата, викат функция от `services/`, показват резултата.
- Права: `@staff_required`, `@front_desk_required`, `@admin_required`, `@customer_required`, `@login_required`
  (от `web/views/base.py`). POST-действията - и `@require_POST`.
- Бизнес действие: `ok, result = try_action(request, lambda: services.x(...), "Съобщение при успех.")` -
  нарушено правило става съобщение за грешка.
- Съобщения: `success()`, `warning()`, `error()` - на български.
- Ремонтите: `can_modify(user, order)` и `current_mechanic_id(user)`.

## Шаблони
- Служители: `{% extends "base.html" %}`; публична част и клиент: `{% extends "site_base.html" %}`.
- Блокове: `content`, `actions` (бутони горе вдясно), `header` (замества заглавната част), `scripts`.
- Заглавие, eyebrow, subtitle - от изгледа в контекста.
- Класовете, id и data-атрибутите в HTML се ползват от CSS и JavaScript - при промяна проверете и двете.
- Филтри (зареждат се сами): `|euro`, `|with_vat`, `|bg`, `|thousands`, `|qty:unit`, `|docnum`, `|service_icon`,
  `|asset`, `|label_of:"RepairStatus"`, `|health_*`, `|rating_*`; тагове `{% plate %}`, `{% chip %}`, `{% status obj %}`,
  `{% field_error form "Name" %}`, `{% page_url n %}`; форми: `{{ form|val:"Name" }}`, `{{ form|fname:"Name" }}`, `{{ form|fid:"Name" }}`.
- **Не ползвайте `|add` с десетични числа** (закръгля до цяло) - сметнете в изгледа или в модела.
- Всяка POST форма има `{% csrf_token %}`. JavaScript заявките взимат токена от `input[name="csrfmiddlewaretoken"]`
  (има го на всяка страница) и го пращат в хедър `X-CSRFToken`.
- Обновяване на живо: `Live.watch(() => презареди частта)` (static/js/live.js).

## Форми
- `web/forms/` - Django форми с имена на полетата като `FullName`, `LicensePlate`; префиксът се отделя с точка
  (`Form.Car.Make`). Съобщенията за грешка са на български.

## Тестове
- `tests/` - unit тестове на бизнес логиката (празна база); `tests/web/` - тестове на страниците с примерните данни
  (фикстури `browser`, `as_role("reception")`, помощник `html()`).
- `python -m pytest` пуска всичко.
