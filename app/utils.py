import csv
import io
from datetime import datetime


def fmt_kop(amount_kop: int | None) -> str:
    amount_kop = amount_kop or 0
    return f"{amount_kop / 100:,.2f} ₽".replace(",", " ")


def fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def rows_to_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)

    for row in rows:
        writer.writerow(row)

    return output.getvalue().encode("utf-8-sig")