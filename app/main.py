from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .reports import get_dashboard_chart_data

from .database import Base, engine, get_db
from . import models
from .auth import (
    verify_password,
    hash_password,
    create_session_token,
    COOKIE_NAME,
    SESSION_MAX_AGE,
)
from .dependencies import get_current_user
from .rbac import (
    ROLE_LABELS,
    ALLOWED_ROLES,
    can_export,
    can_manage_users,
    can_view_audit,
)
from .masking import (
    mask_full_name,
    mask_email,
    mask_phone,
    mask_address,
    mask_card,
)
from .utils import fmt_kop, fmt_dt, rows_to_csv
from .seed import seed_all
from .reports import (
    PAYMENT_METHOD_LABELS,
    ORDER_STATUS_LABELS,
    REFUND_TYPE_LABELS,
    order_payment_totals,
    get_summary,
    summary_rows,
    get_daily_rows,
    get_payment_method_rows,
    get_refund_rows,
    get_partial_refund_rows,
    get_order_report_rows,
    get_order_export_rows,
    get_dashboard_chart_data,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Finance Reports")

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    seed_all()


def render_page(
    request: Request,
    user,
    template_name: str,
    title: str,
    **kwargs,
):
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "user": user,
            "title": title,
            "role_label": ROLE_LABELS.get(user.role, user.role) if user else "",
            **kwargs,
        },
    )


@app.get("/", response_class=HTMLResponse)
def root(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)

    return render_page(request, None, "login.html", "Вход")


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.is_active == True)
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
        db.add(
            models.AuditLog(
                user_id=user.id if user else None,
                action="login_failed",
                details=f"username={username}",
            )
        )
        db.commit()

        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "title": "Вход",
                "error": "Неверный логин или пароль",
            },
            status_code=400,
        )

    token = create_session_token(user.id)

    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )

    db.add(
        models.AuditLog(
            user_id=user.id,
            action="login",
            details="",
        )
    )
    db.commit()

    return response


@app.post("/logout")
def logout(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user:
        db.add(
            models.AuditLog(
                user_id=user.id,
                action="logout",
                details="",
            )
        )
        db.commit()

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    summary = get_summary(db)
    charts = get_dashboard_chart_data(db)

    cards = [
        {"label": "Всего заказов", "value": summary["total_orders"]},
        {"label": "Оплачено заказов", "value": summary["paid_orders"]},
        {"label": "Сумма оплат", "value": fmt_kop(summary["paid_sum_kop"])},
        {"label": "Сумма возвратов", "value": fmt_kop(summary["refund_sum_kop"])},
        {"label": "Чистая выручка", "value": fmt_kop(summary["net_kop"])},
        {"label": "Средний чек", "value": fmt_kop(summary["avg_check_kop"])},
        {"label": "Комиссия", "value": fmt_kop(summary["fee_sum_kop"])},
        {"label": "Частичных возвратов", "value": summary["partial_refunds_count"]},
    ]

    return render_page(
        request,
        user,
        "dashboard.html",
        "Дашборд",
        cards=cards,
        charts=charts,
    )


@app.get("/orders", response_class=HTMLResponse)
def orders_list(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()

    items = []

    for order in orders:
        paid, refunded = order_payment_totals(order)

        items.append(
            {
                "id": order.id,
                "order_number": order.order_number,
                "created_at": fmt_dt(order.created_at),
                "customer": mask_full_name(
                    order.customer.full_name if order.customer else "",
                    user,
                ),
                "total": fmt_kop(order.total_amount_kop),
                "paid": fmt_kop(paid),
                "refunded": fmt_kop(refunded),
                "status": ORDER_STATUS_LABELS.get(order.status, order.status),
            }
        )

    return render_page(request, user, "orders_list.html", "Заказы", items=items)


@app.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(
    order_id: int,
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    order = db.query(models.Order).filter(models.Order.id == order_id).first()

    if not order:
        return HTMLResponse("Заказ не найден", status_code=404)

    customer = order.customer

    customer_data = {
        "full_name": mask_full_name(customer.full_name if customer else "", user),
        "email": mask_email(customer.email if customer else "", user),
        "phone": mask_phone(customer.phone if customer else "", user),
        "address": mask_address(customer.address if customer else "", user),
    }

    payment_rows = []

    for payment in order.payments:
        payment_rows.append(
            [
                payment.payment_id,
                PAYMENT_METHOD_LABELS.get(payment.payment_method, payment.payment_method),
                fmt_dt(payment.created_at),
                fmt_dt(payment.paid_at),
                fmt_kop(payment.amount_kop),
                payment.status,
                mask_card(payment.card_masked, payment.card_last4, user),
                fmt_kop(payment.fee_kop),
            ]
        )

    refund_rows = []

    for payment in order.payments:
        for refund in payment.refunds:
            refund_rows.append(
                [
                    refund.refund_id,
                    fmt_dt(refund.created_at),
                    fmt_kop(refund.amount_kop),
                    REFUND_TYPE_LABELS.get(refund.refund_type, refund.refund_type),
                    refund.status,
                    refund.reason or "",
                ]
            )

    paid, refunded = order_payment_totals(order)

    totals = {
        "paid": fmt_kop(paid),
        "refunded": fmt_kop(refunded),
        "net": fmt_kop(paid - refunded),
    }

    return render_page(
        request,
        user,
        "order_detail.html",
        f"Заказ {order.order_number}",
        order=order,
        customer=customer_data,
        payment_rows=payment_rows,
        refund_rows=refund_rows,
        totals=totals,
        ORDER_STATUS_LABELS=ORDER_STATUS_LABELS,
    )


@app.get("/reports", response_class=HTMLResponse)
def reports_index(
    request: Request,
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    return render_page(
        request,
        user,
        "reports_index.html",
        "Отчёты",
        can_export=can_export(user),
    )


@app.get("/reports/summary", response_class=HTMLResponse)
def report_summary(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    summary = get_summary(db)
    rows = summary_rows(summary)

    return render_page(
        request,
        user,
        "table.html",
        "Сводный отчёт",
        headers=["Показатель", "Значение"],
        rows=rows,
    )


@app.get("/reports/daily", response_class=HTMLResponse)
def report_daily(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    rows = get_daily_rows(db)

    return render_page(
        request,
        user,
        "table.html",
        "Отчёт по дням",
        headers=[
            "Дата",
            "Оплат",
            "Сумма оплат",
            "Возвратов",
            "Сумма возвратов",
            "Нетто",
        ],
        rows=rows,
    )


@app.get("/reports/payment-methods", response_class=HTMLResponse)
def report_payment_methods(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    rows = get_payment_method_rows(db)

    return render_page(
        request,
        user,
        "table.html",
        "Отчёт по способам оплаты",
        headers=[
            "Способ оплаты",
            "Количество",
            "Сумма",
            "Комиссия",
            "Сумма без комиссии",
        ],
        rows=rows,
    )


@app.get("/reports/refunds", response_class=HTMLResponse)
def report_refunds(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    rows = get_refund_rows(db)

    return render_page(
        request,
        user,
        "table.html",
        "Отчёт по возвратам",
        headers=["Тип возврата", "Количество", "Сумма"],
        rows=rows,
    )


@app.get("/reports/partial-refunds", response_class=HTMLResponse)
def report_partial_refunds(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    rows = get_partial_refund_rows(db)

    return render_page(
        request,
        user,
        "table.html",
        "Отчёт по частичным возвратам",
        headers=[
            "Заказ",
            "Оплачено",
            "Возвращено",
            "Остаток",
            "Процент возврата",
        ],
        rows=rows,
    )


@app.get("/reports/orders", response_class=HTMLResponse)
def report_orders(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    rows = get_order_report_rows(db, user)

    return render_page(
        request,
        user,
        "table.html",
        "Отчёт по заказам",
        headers=[
            "Заказ",
            "Дата",
            "Клиент",
            "Сумма заказа",
            "Оплачено",
            "Возвращено",
            "Итог",
            "Статус",
        ],
        rows=rows,
    )


@app.get("/reports/export/{name}")
def export_report(
    name: str,
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not can_export(user):
        return HTMLResponse("Экспорт недоступен для вашей роли", status_code=403)

    if name == "summary":
        headers = ["Показатель", "Значение"]
        rows = summary_rows(get_summary(db))

    elif name == "daily":
        headers = [
            "Дата",
            "Оплат",
            "Сумма оплат",
            "Возвратов",
            "Сумма возвратов",
            "Нетто",
        ]
        rows = get_daily_rows(db)

    elif name == "payment_methods":
        headers = [
            "Способ оплаты",
            "Количество",
            "Сумма",
            "Комиссия",
            "Сумма без комиссии",
        ]
        rows = get_payment_method_rows(db)

    elif name == "refunds":
        headers = ["Тип возврата", "Количество", "Сумма"]
        rows = get_refund_rows(db)

    elif name == "partial_refunds":
        headers = [
            "Заказ",
            "Оплачено",
            "Возвращено",
            "Остаток",
            "Процент возврата",
        ]
        rows = get_partial_refund_rows(db)

    elif name == "orders":
        headers = [
            "Заказ",
            "Дата",
            "Клиент",
            "Email",
            "Телефон",
            "Адрес",
            "Сумма заказа",
            "Оплачено",
            "Возвращено",
            "Итог",
            "Статус",
        ]
        rows = get_order_export_rows(db, user)

    else:
        return HTMLResponse("Неизвестный отчёт", status_code=404)

    content = rows_to_csv(headers, rows)

    db.add(
        models.AuditLog(
            user_id=user.id,
            action="export",
            details=name,
        )
    )
    db.commit()

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={name}.csv",
        },
    )


@app.get("/users", response_class=HTMLResponse)
def users_list(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not can_manage_users(user):
        return HTMLResponse("Доступ запрещён", status_code=403)

    users = db.query(models.User).order_by(models.User.id).all()

    return render_page(
        request,
        user,
        "users_list.html",
        "Пользователи",
        users=users,
        ROLE_LABELS=ROLE_LABELS,
    )


@app.get("/users/create", response_class=HTMLResponse)
def users_create_page(
    request: Request,
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not can_manage_users(user):
        return HTMLResponse("Доступ запрещён", status_code=403)

    return render_page(
        request,
        user,
        "users_create.html",
        "Создать пользователя",
        roles=list(ROLE_LABELS.items()),
        error=None,
    )


@app.post("/users/create", response_class=HTMLResponse)
def users_create_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not can_manage_users(user):
        return HTMLResponse("Доступ запрещён", status_code=403)

    error = None

    if role not in ALLOWED_ROLES:
        error = "Недопустимая роль"

    if len(password) < 8:
        error = "Пароль должен содержать минимум 8 символов"

    exists = db.query(models.User).filter(models.User.username == username).first()
    if exists:
        error = "Пользователь с таким логином уже существует"

    if error:
        return templates.TemplateResponse(
            "users_create.html",
            {
                "request": request,
                "user": user,
                "title": "Создать пользователя",
                "roles": list(ROLE_LABELS.items()),
                "error": error,
            },
            status_code=400,
        )

    new_user = models.User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )

    db.add(new_user)
    db.commit()

    db.add(
        models.AuditLog(
            user_id=user.id,
            action="user_created",
            details=f"username={username}, role={role}",
        )
    )
    db.commit()

    return RedirectResponse("/users", status_code=303)


@app.get("/audit", response_class=HTMLResponse)
def audit_list(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not can_view_audit(user):
        return HTMLResponse("Доступ запрещён", status_code=403)

    logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(200)
        .all()
    )

    rows = []

    for log in logs:
        rows.append(
            [
                fmt_dt(log.created_at),
                log.user.username if log.user else "—",
                log.action,
                log.details or "",
            ]
        )

    return render_page(
        request,
        user,
        "table.html",
        "Журнал аудита",
        headers=["Дата", "Пользователь", "Событие", "Детали"],
        rows=rows,
    )