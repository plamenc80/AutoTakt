"""Експорт на справката в Excel (с openpyxl)."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

MONEY_FORMAT = '#,##0.00 "€"'
HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")


def _table(sheet, start_row, title, headers, rows, money_columns):
    sheet.cell(start_row, 1, title).font = Font(bold=True)
    for c, header in enumerate(headers, start=1):
        cell = sheet.cell(start_row + 1, c, header)
        cell.font, cell.fill = Font(bold=True), HEADER_FILL
    for r, row in enumerate(rows, start=start_row + 2):
        for c, value in enumerate(row, start=1):
            cell = sheet.cell(r, c, float(value) if hasattr(value, "quantize") else value)
            if c in money_columns:
                cell.number_format = MONEY_FORMAT


def _fit_columns(sheet):
    for column in sheet.columns:
        width = max((len(str(cell.value)) for cell in column if cell.value is not None), default=8)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(60, width + 2)


def export_period_report(report):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Обобщение"
    summary["A1"] = f"Справка за периода {report.start:%d.%m.%Y} - {report.end:%d.%m.%Y}"
    summary["A1"].font = Font(bold=True, size=14)
    rows = [("Приходи (постъпили плащания)", report.total_revenue, True),
            ("Стойност на труда (без ДДС)", report.total_labor, True),
            ("Стойност на частите (без ДДС)", report.total_parts, True),
            ("Брой завършени ремонти", report.repairs_count, False),
            ("Средна стойност на ремонт (без ДДС)", report.average_repair_value, True)]
    for i, (label, value, money) in enumerate(rows, start=3):
        summary.cell(i, 1, label)
        cell = summary.cell(i, 2, float(value) if money else int(value))
        if money:
            cell.number_format = MONEY_FORMAT

    _table(summary, 10, "Приходи по месеци", ["Месец", "Приходи", "Брой платени ремонти"],
           [(m.label, m.amount, m.repairs_count) for m in report.revenue_by_month], {2})
    _table(summary, 14 + len(report.revenue_by_month), "Приходи по начин на плащане", ["Начин на плащане", "Сума", "Брой плащания"],
           [(m.method_name, m.amount, m.count) for m in report.by_payment_method], {2})
    _table(workbook.create_sheet("Услуги"), 1, "Най-често извършвани услуги", ["Услуга", "Брой", "Стойност (без ДДС)"],
           [(s.service_name, s.times_performed, s.revenue) for s in report.top_services], {3})
    _table(workbook.create_sheet("Части"), 1, "Вложени авточасти",
           ["Част", "Каталожен №", "Вложени", "Стойност (без ДДС)", "Наличност", "Мин. наличност"],
           [(p.part_name, p.part_number, p.quantity_used, p.revenue, p.in_stock, p.min_stock) for p in report.parts_usage], {4})
    _table(workbook.create_sheet("Механици"), 1, "Натовареност на механиците",
           ["Механик", "Брой ремонти", "Стойност на труда", "Средно време (ч)"],
           [(m.mechanic_name, m.repairs_count, m.labor_revenue, m.average_hours) for m in report.mechanics], {3})
    for sheet in workbook.worksheets:
        _fit_columns(sheet)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
