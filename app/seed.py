import random
from datetime import datetime, timedelta

from .database import SessionLocal
from .models import User, Customer, Order, Payment, Refund, AuditLog
from .auth import hash_password
from .rbac import ADMIN, SENIOR_FINANCE, FINANCE_INTERN


def create_users(db) -> None:
    users = [
        ("admin", "Admin123!", ADMIN),
        ("senior", "Senior123!", SENIOR_FINANCE),
        ("intern", "Intern123!", FINANCE_INTERN),
    ]

    for username, password, role in users:
        exists = db.query(User).filter(User.username == username).first()
        if exists:
            continue

        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
        )


def create_orders(db) -> None:
    if db.query(Order).count() > 0:
        return

    random.seed(42)

    last_names = [
        "Иванов",
        "Петров",
        "Сидоров",
        "Кузнецов",
        "Смирнов",
        "Волков",
        "Фёдоров",
        "Морозов",
        "Никитин",
        "Орлов",
    ]

    first_names = [
        "Иван",
        "Пётр",
        "Алексей",
        "Сергей",
        "Дмитрий",
        "Андрей",
        "Михаил",
        "Николай",
        "Егор",
        "Павел",
    ]

    patronymics = [
        "Иванович",
        "Петрович",
        "Сергеевич",
        "Алексеевич",
        "Дмитриевич",
        "Андреевич",
        "Михайлович",
        "Николаевич",
        "Егорович",
        "Павлович",
    ]

    streets = [
        "ул. Ленина",
        "пр. Мира",
        "ул. Сахалинская",
        "ул. Комсомольская",
        "ул. Пограничная",
        "ул. Советская",
        "пр. Победы",
        "ул. Горького",
    ]

    payment_methods = ["bank_card", "sbp", "yoo_money"]
    base_date = datetime(2026, 10, 1, 9, 0, 0)

    for index in range(1, 101):
        last_name = random.choice(last_names)
        first_name = random.choice(first_names)
        patronymic = random.choice(patronymics)

        full_name = f"{last_name} {first_name} {patronymic}"
        email = f"user{index:03d}@example.com"
        phone = f"+7924{random.randint(1000000, 9999999)}"
        address = (
            f"г. Южно-Сахалинск, {random.choice(streets)}, "
            f"д. {random.randint(1, 60)}, кв. {random.randint(1, 120)}"
        )

        customer = Customer(
            full_name=full_name,
            email=email,
            phone=phone,
            address=address,
        )

        created_at = base_date + timedelta(
            days=(index - 1) % 30,
            hours=random.randint(8, 12),
            minutes=random.randint(0, 59),
        )

        total_amount_kop = random.randint(30_000, 3_000_000)

        if index <= 65:
            status = "paid"
        elif index <= 80:
            status = "partially_refunded"
        elif index <= 90:
            status = "fully_refunded"
        else:
            status = "canceled"

        order = Order(
            order_number=f"IM-{1000 + index}",
            created_at=created_at,
            status=status,
            customer=customer,
            total_amount_kop=total_amount_kop,
            currency="RUB",
            comment="Демо-заказ интернет-магазина",
        )

        db.add(order)

        if index <= 90:
            payment_method = payment_methods[(index - 1) % 3]
            fee_kop = int(
                total_amount_kop * 0.03
                if payment_method == "yoo_money"
                else total_amount_kop * 0.02
            )

            paid_at = created_at + timedelta(minutes=random.randint(5, 90))

            card_last4 = None
            card_masked = None

            if payment_method == "bank_card":
                card_last4 = f"{random.randint(0, 9999):04d}"
                card_masked = f"2200 70** **** {card_last4}"

            payment = Payment(
                payment_id=f"pay_{index:04d}",
                order=order,
                payment_method=payment_method,
                amount_kop=total_amount_kop,
                currency="RUB",
                status="succeeded",
                created_at=created_at,
                paid_at=paid_at,
                card_last4=card_last4,
                card_masked=card_masked,
                fee_kop=fee_kop,
            )

            db.add(payment)

            if 66 <= index <= 80:
                refund_total = int(total_amount_kop * random.uniform(0.25, 0.65))

                if index <= 70:
                    amount_1 = int(refund_total * 0.6)
                    amount_2 = refund_total - amount_1

                    db.add(
                        Refund(
                            refund_id=f"ref_{index:04d}_1",
                            payment=payment,
                            created_at=paid_at + timedelta(days=1, hours=2),
                            amount_kop=amount_1,
                            refund_type="partial",
                            status="succeeded",
                            reason="Возврат части товаров",
                        )
                    )

                    db.add(
                        Refund(
                            refund_id=f"ref_{index:04d}_2",
                            payment=payment,
                            created_at=paid_at + timedelta(days=2, hours=5),
                            amount_kop=amount_2,
                            refund_type="partial",
                            status="succeeded",
                            reason="Возврат части товаров",
                        )
                    )
                else:
                    db.add(
                        Refund(
                            refund_id=f"ref_{index:04d}",
                            payment=payment,
                            created_at=paid_at + timedelta(days=1, hours=3),
                            amount_kop=refund_total,
                            refund_type="partial",
                            status="succeeded",
                            reason="Возврат части товаров",
                        )
                    )

            elif 81 <= index <= 90:
                db.add(
                    Refund(
                        refund_id=f"ref_{index:04d}",
                        payment=payment,
                        created_at=paid_at + timedelta(days=2, hours=4),
                        amount_kop=total_amount_kop,
                        refund_type="full",
                        status="succeeded",
                        reason="Полный возврат заказа",
                    )
                )
        else:
            payment_method = payment_methods[(index - 1) % 3]

            payment = Payment(
                payment_id=f"pay_{index:04d}",
                order=order,
                payment_method=payment_method,
                amount_kop=total_amount_kop,
                currency="RUB",
                status="canceled",
                created_at=created_at,
                paid_at=None,
                card_last4=None,
                card_masked=None,
                fee_kop=0,
            )

            db.add(payment)


def seed_all() -> None:
    db = SessionLocal()
    try:
        create_users(db)
        create_orders(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()