"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_superadmin
from app.database.session import get_db
from app.database.models import User
from app.schemas.shop import (
    AddressBody,
    CartAdd,
    CartUpdate,
    PreviewBody,
    CheckoutBody,
    OfferBody,
    ShippingBody,
)
from app.services import addresses as addresses_service
from app.services import cart as cart_service
from app.services import orders as orders_service
from app.services import offers as offers_service

router = APIRouter(
    prefix="/api/shop", tags=["shopping"], dependencies=[Depends(get_current_user)]
)

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["order-management"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("/addresses")
def addresses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return addresses_service.addresses(db, user)


@router.post("/addresses", status_code=201)
def add_address(
    body: AddressBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return addresses_service.add_address(body, db, user)


@router.put("/addresses/{address_id}")
def edit_address(
    address_id: int,
    body: AddressBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return addresses_service.edit_address(address_id, body, db, user)


@router.delete("/addresses/{address_id}", status_code=204)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return addresses_service.delete_address(address_id, db, user)


@router.get("/cart")
def cart(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return cart_service.cart(db, user)


@router.post("/cart", status_code=201)
def add_cart(
    body: CartAdd, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return cart_service.add_cart(body, db, user)


@router.patch("/cart/{item_id}")
def update_cart(
    item_id: int,
    body: CartUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return cart_service.update_cart(item_id, body, db, user)


@router.delete("/cart/{item_id}", status_code=204)
def delete_cart(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return cart_service.delete_cart(item_id, db, user)


@router.post("/checkout/preview")
def preview(body: PreviewBody, db: Session = Depends(get_db)):
    return orders_service.preview(body, db)


@router.post("/orders", status_code=201)
def checkout(
    body: CheckoutBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return orders_service.checkout(body, db, user)


@router.get("/orders")
def orders(
    status: str = Query(
        "", pattern="^(|pending_payment|paid|shipped|completed|cancelled|refunded)$"
    ),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return orders_service.orders(status, page, db, user)


@router.get("/orders/{order_id}")
def detail(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return orders_service.detail(order_id, db, user)


@router.post("/orders/{order_id}/pay")
def pay(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return orders_service.pay(order_id, db, user)


@router.post("/orders/{order_id}/cancel")
def cancel(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return orders_service.cancel(order_id, db, user)


@router.post("/orders/{order_id}/complete")
def confirm_receipt(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return orders_service.confirm_receipt(order_id, db, user)


@admin_router.get("/offers/{product_id}")
def get_offer(product_id: int, db: Session = Depends(get_db)):
    return offers_service.get_offer(product_id, db)


@admin_router.put("/offers/{product_id}")
def set_offer(product_id: int, body: OfferBody, db: Session = Depends(get_db)):
    return offers_service.set_offer(product_id, body, db)


@admin_router.get("/orders")
def admin_orders(
    status: str = Query(
        "", pattern="^(|pending_payment|paid|shipped|completed|cancelled|refunded)$"
    ),
    q: str = Query("", max_length=40),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    return orders_service.admin_orders(status, q, page, db)


@admin_router.post("/orders/{order_id}/ship")
def ship(order_id: int, body: ShippingBody, db: Session = Depends(get_db)):
    return orders_service.ship(order_id, body, db)
