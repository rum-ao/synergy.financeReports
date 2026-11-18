from sqlalchemy import func

from .models import Order, Payment, Refund
from .masking import (
    mask_full_name,
    mask_email,
    mask_phone,
    mask_address,
)
from .utils import fmt_kop, fmt_dt

PAYMENT_METHOD_LABELS = {
    "bank_card": "Банковская карта",
    "sbp": "СБП",
    "yoo_money": "ЮMoney",
}

ORDER_STATUS_LABELS = {
    "paid": "Оплачен",
    "partially_refunded": "Частичный возврат",
    "fully_refunded": "Полный возврат",
    "canceled": "Отменён",
}

REFUND_TYPE_LABELS = {
    "full": "Полный",
    "partial": "Частичный",
}


def order_payment_totals(order: Order) -> tuple[int, int]:
    paid_kop = sum(
        payment.amount_kop
        for payment in order.payments
        if payment.status == "succeeded"
    )

    refunded_kop = sum(
        refund.amount_kop
        for payment in order.payments
        for refund in payment.refunds
        if refund.status == "succeeded"
    )

    return paid_kop, refunded_kop


def get_summary(db) -> dict:
    total_orders = db.query(func.count(Order.id)).scalar() or 0

    paid_orders = (
        db.query(Order.id)
        .join(Payment, Payment.order_id == Order.id)
        .filter(Payment.status == "succeeded")
        .distinct()
        .count()
    )

    paid_sum_kop = (
        db.query(func.coalesce(func.sum(Payment.amount_kop), 0))
        .filter(Payment.status == "succeeded")
        .scalar()
    )

    fee_sum_kop = (
        db.query(func.coalesce(func.sum(Payment.fee_kop), 0))
        .filter(Payment.status == "succeeded")
        .scalar()
    )

    refund_sum_kop = (
        db.query(func.coalesce(func.sum(Refund.amount_kop), 0))
        .filter(Refund.status == "succeeded")
        .scalar()
    )

    net_kop = paid_sum_kop - refund_sum_kop

    full_refunds_count = (
        db.query(func.count(Refund.id))
        .filter(Refund.status == "succeeded", Refund.refund_type == "full")
        .scalar()
    )

    partial_refunds_count = (
        db.query(func.count(Refund.id))
        .filter(Refund.status == "succeeded", Refund.refund_type == "partial")
        .scalar()
    )

    avg_check_kop = paid_sum_kop // paid_orders if paid_orders else 0

    return {
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "paid_sum_kop": paid_sum_kop,
        "fee_sum_kop": fee_sum_kop,
        "refund_sum_kop": refund_sum_kop,
        "net_kop": net_kop,
        "avg_check_kop": avg_check_kop,
        "full_refunds_count": full_refunds_count,
        "partial_refunds_count": partial_refunds_count,
    }


def summary_rows(summary: dict) -> list[list[str]]:
    return [
        ["Всего заказов", str(summary["total_orders"])],
        ["Оплачено заказов", str(summary["paid_orders"])],
        ["Сумма успешных оплат", fmt_kop(summary["paid_sum_kop"])],
        ["Сумма комиссии", fmt_kop(summary["fee_sum_kop"])],
        ["Сумма возвратов", fmt_kop(summary["refund_sum_kop"])],
        ["Чистая выручка", fmt_kop(summary["net_kop"])],
        ["Средний чек", fmt_kop(summary["avg_check_kop"])],
        ["Полных возвратов", str(summary["full_refunds_count"])],
        ["Частичных возвратов", str(summary["partial_refunds_count"])],
    ]


def get_daily_rows(db) -> list[list[str]]:
    payments = (
        db.query(
            func.date(Payment.paid_at).label("day"),
            func.count(Payment.id),
            func.sum(Payment.amount_kop),
        )
        .filter(Payment.status == "succeeded", Payment.paid_at != None)
        .group_by(func.date(Payment.paid_at))
        .all()
    )

    refunds = (
        db.query(
            func.date(Refund.created_at).label("day"),
            func.count(Refund.id),
            func.sum(Refund.amount_kop),
        )
        .filter(Refund.status == "succeeded")
        .group_by(func.date(Refund.created_at))
        .all()
    )

    data = {}

    for day, count, amount in payments:
        data[day] = {
            "payments_count": count,
            "paid_kop": amount or 0,
            "refunds_count": 0,
            "refund_kop": 0,
        }

    for day, count, amount in refunds:
        if day not in data:
            data[day] = {
                "payments_count": 0,
                "paid_kop": 0,
                "refunds_count": 0,
                "refund_kop": 0,
            }

        data[day]["refunds_count"] += count
        data[day]["refund_kop"] += amount or 0

    rows = []

    for day in sorted(data.keys()):
        item = data[day]
        net = item["paid_kop"] - item["refund_kop"]

        rows.append(
            [
                day,
                str(item["payments_count"]),
                fmt_kop(item["paid_kop"]),
                str(item["refunds_count"]),
                fmt_kop(item["refund_kop"]),
                fmt_kop(net),
            ]
        )

    return rows


def get_payment_method_rows(db) -> list[list[str]]:
    rows_query = (
        db.query(
            Payment.payment_method,
            func.count(Payment.id),
            func.sum(Payment.amount_kop),
            func.sum(Payment.fee_kop),
        )
        .filter(Payment.status == "succeeded")
        .group_by(Payment.payment_method)
        .all()
    )

    rows = []

    for method, count, amount, fee in rows_query:
        amount = amount or 0
        fee = fee or 0

        rows.append(
            [
                PAYMENT_METHOD_LABELS.get(method, method),
                str(count),
                fmt_kop(amount),
                fmt_kop(fee),
                fmt_kop(amount - fee),
            ]
        )

    return rows


def get_refund_rows(db) -> list[list[str]]:
    rows_query = (
        db.query(
            Refund.refund_type,
            func.count(Refund.id),
            func.sum(Refund.amount_kop),
        )
        .filter(Refund.status == "succeeded")
        .group_by(Refund.refund_type)
        .all()
    )

    rows = []

    for refund_type, count, amount in rows_query:
        rows.append(
            [
                REFUND_TYPE_LABELS.get(refund_type, refund_type),
                str(count),
                fmt_kop(amount or 0),
            ]
        )

    return rows


def get_partial_refund_rows(db) -> list[list[str]]:
    rows_query = (
        db.query(
            Order.order_number,
            func.sum(Payment.amount_kop).label("paid"),
            func.sum(Refund.amount_kop).label("refunded"),
        )
        .join(Payment, Payment.order_id == Order.id)
        .join(Refund, Refund.payment_id == Payment.id)
        .filter(
            Payment.status == "succeeded",
            Refund.status == "succeeded",
            Refund.refund_type == "partial",
        )
        .group_by(Order.id, Order.order_number)
        .all()
    )

    rows = []

    for order_number, paid, refunded in rows_query:
        paid = paid or 0
        refunded = refunded or 0
        rest = paid - refunded

        percent = f"{(refunded / paid * 100):.1f}%" if paid else "0.0%"

        rows.append(
            [
                order_number,
                fmt_kop(paid),
                fmt_kop(refunded),
                fmt_kop(rest),
                percent,
            ]
        )

    return rows


def get_order_report_rows(db, user) -> list[list[str]]:
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    rows = []

    for order in orders:
        paid, refunded = order_payment_totals(order)

        customer_name = order.customer.full_name if order.customer else ""

        rows.append(
            [
                order.order_number,
                fmt_dt(order.created_at),
                mask_full_name(customer_name, user),
                fmt_kop(order.total_amount_kop),
                fmt_kop(paid),
                fmt_kop(refunded),
                fmt_kop(paid - refunded),
                ORDER_STATUS_LABELS.get(order.status, order.status),
            ]
        )

    return rows


def get_order_export_rows(db, user) -> list[list[str]]:
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    rows = []

    for order in orders:
        paid, refunded = order_payment_totals(order)
        customer = order.customer

        rows.append(
            [
                order.order_number,
                fmt_dt(order.created_at),
                mask_full_name(customer.full_name if customer else "", user),
                mask_email(customer.email if customer else "", user),
                mask_phone(customer.phone if customer else "", user),
                mask_address(customer.address if customer else "", user),
                fmt_kop(order.total_amount_kop),
                fmt_kop(paid),
                fmt_kop(refunded),
                fmt_kop(paid - refunded),
                ORDER_STATUS_LABELS.get(order.status, order.status),
            ]
        )

    return rows


def get_dashboard_chart_data(db) -> dict:
    # --- Динамика по дням ---
    payment_rows = (
        db.query(
            func.date(Payment.paid_at).label("day"),
            func.sum(Payment.amount_kop),
        )
        .filter(Payment.status == "succeeded", Payment.paid_at != None)
        .group_by(func.date(Payment.paid_at))
        .all()
    )

    refund_rows = (
        db.query(
            func.date(Refund.created_at).label("day"),
            func.sum(Refund.amount_kop),
        )
        .filter(Refund.status == "succeeded")
        .group_by(func.date(Refund.created_at))
        .all()
    )

    days = {}

    for day, amount in payment_rows:
        days.setdefault(day, {"paid": 0, "refunded": 0})
        days[day]["paid"] = amount or 0

    for day, amount in refund_rows:
        days.setdefault(day, {"paid": 0, "refunded": 0})
        days[day]["refunded"] = amount or 0

    daily_labels = []
    daily_paid = []
    daily_refunded = []
    daily_refund_share = []

    for day in sorted(days.keys()):
        item = days[day]
        paid_rub = round(item["paid"] / 100, 2)
        refunded_rub = round(item["refunded"] / 100, 2)
        share = round(refunded_rub / paid_rub * 100, 1) if paid_rub else 0.0

        daily_labels.append(str(day))
        daily_paid.append(paid_rub)
        daily_refunded.append(refunded_rub)
        daily_refund_share.append(share)

    # --- Способы оплаты ---
    method_rows = (
        db.query(Payment.payment_method, func.sum(Payment.amount_kop))
        .filter(Payment.status == "succeeded")
        .group_by(Payment.payment_method)
        .all()
    )

    method_labels = []
    method_values = []

    for method, amount in method_rows:
        method_labels.append(PAYMENT_METHOD_LABELS.get(method, method))
        method_values.append(round((amount or 0) / 100, 2))

    # --- Возвраты по типам ---
    refund_type_rows = (
        db.query(Refund.refund_type, func.sum(Refund.amount_kop))
        .filter(Refund.status == "succeeded")
        .group_by(Refund.refund_type)
        .all()
    )

    refund_labels = []
    refund_values = []

    for refund_type, amount in refund_type_rows:
        refund_labels.append(REFUND_TYPE_LABELS.get(refund_type, refund_type))
        refund_values.append(round((amount or 0) / 100, 2))

    # --- Заказы по статусам ---
    status_rows = (
        db.query(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .all()
    )

    status_labels = []
    status_values = []

    for status, count in status_rows:
        status_labels.append(ORDER_STATUS_LABELS.get(status, status))
        status_values.append(count)

    return {
        "daily": {
            "labels": daily_labels,
            "paid": daily_paid,
            "refunded": daily_refunded,
            "refund_share": daily_refund_share,
        },
        "methods": {
            "labels": method_labels,
            "values": method_values,
        },
        "refunds": {
            "labels": refund_labels,
            "values": refund_values,
        },
        "statuses": {
            "labels": status_labels,
            "values": status_values,
        },
    }