"""Authenticated demo shopping with server prices, inventory locks and order snapshots."""
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_superadmin
from app.database.session import get_db
from app.database.models import User
from app.database.catalog_models import Product, ProductImage
from app.database.shop_models import CartItem, SaleOffer, ShippingAddress, ShopOrder, ShopOrderItem
from app.api.catalog import VISIBLE_STATUSES, product_query, serialize_products
from app.services.aftersales import active_refund,latest_summary
from app.database.aftersales_models import ShipmentReminder

router = APIRouter(prefix='/api/shop', tags=['shopping'], dependencies=[Depends(get_current_user)])
admin_router = APIRouter(prefix='/api/admin', tags=['order-management'], dependencies=[Depends(require_superadmin)])
PositiveId = Annotated[StrictInt, Field(gt=0)]
Quantity = Annotated[StrictInt, Field(ge=1, le=99)]
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AddressBody(StrictBody):
    recipient: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=6, max_length=30, pattern=r'^\+?[0-9 ()-]+$')
    region: str = Field(min_length=2, max_length=200)
    detail: str = Field(min_length=3, max_length=500)
    postal_code: str = Field(default='', max_length=20)
    is_default: bool = False

    @field_validator('recipient','phone','region','detail')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('必填信息不能为空')
        return value.strip()

    @field_validator('phone')
    @classmethod
    def phone_digits(cls, value):
        if not 6 <= sum(char.isdigit() for char in value) <= 20:
            raise ValueError('请输入有效联系电话')
        return value


class CartAdd(StrictBody):
    product_id: PositiveId
    quantity: Quantity = 1


class CartUpdate(StrictBody):
    quantity: Quantity


class Selection(StrictBody):
    product_id: PositiveId
    quantity: Quantity


class PricedSelection(Selection):
    expected_price: Money
    currency: str = Field(pattern='^(USD|CNY|EUR|GBP|JPY|HKD)$')


class PreviewBody(StrictBody):
    items: list[Selection] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique(self):
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError('商品不能重复')
        return self


class CheckoutBody(PreviewBody):
    items: list[PricedSelection] = Field(min_length=1, max_length=50)
    address_id: PositiveId
    cart_item_ids: list[PositiveId] = Field(default_factory=list, max_length=50)
    request_key: str = Field(min_length=16, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    note: str = Field(default='', max_length=500)


class OfferBody(StrictBody):
    price: Money
    currency: str = Field(pattern='^(USD|CNY|EUR|GBP|JPY|HKD)$')
    stock: Annotated[StrictInt, Field(ge=0, le=1000000)]
    is_active: bool
    updated_at: datetime | None = None


class ShippingBody(StrictBody):
    carrier: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(min_length=3, max_length=100, pattern=r'^[a-zA-Z0-9-]+$')


def now():
    return datetime.now(timezone.utc)


def lock_user(db, user):
    db.execute(select(User.id).where(User.id == user.id).with_for_update())


def address_data(address):
    return {key: getattr(address, key) for key in ('id','recipient','phone','region','detail','postal_code','is_default')}


def owned_address(db, user, address_id):
    address = db.scalar(select(ShippingAddress).where(ShippingAddress.id == address_id, ShippingAddress.user_id == user.id))
    if address is None:
        raise HTTPException(404, '收货地址不存在')
    return address


def release_stock(db, orders):
    quantities = defaultdict(int)
    for item in db.scalars(select(ShopOrderItem).where(ShopOrderItem.order_id.in_([o.id for o in orders]))):
        quantities[item.product_id] += item.quantity
    if quantities:
        for offer in db.scalars(select(SaleOffer).where(SaleOffer.product_id.in_(quantities)).order_by(SaleOffer.product_id).with_for_update()):
            offer.stock += quantities[offer.product_id]
            offer.updated_at = now()


def expire_orders(db):
    # Lazy reclamation on shop access; row locks make repeated/parallel reclamation safe.
    expired = db.scalars(select(ShopOrder).where(ShopOrder.status == 'pending_payment', ShopOrder.expires_at <= now())
                        .order_by(ShopOrder.id).limit(500).with_for_update(skip_locked=True)).all()
    if expired:
        release_stock(db, expired)
        for order in expired:
            order.status = 'cancelled'; order.cancelled_at = now(); order.cancel_reason = '超时未支付'
        db.flush()


def quote(db, items, lock=False):
    ids = sorted(item.product_id for item in items)
    products_query = select(Product).where(Product.id.in_(ids), Product.status.in_(VISIBLE_STATUSES)).order_by(Product.id)
    if lock:
        products_query = products_query.with_for_update(read=True)
    products = {p.id:p for p in db.scalars(products_query)}
    offers_query = select(SaleOffer).where(SaleOffer.product_id.in_(ids)).order_by(SaleOffer.product_id)
    if lock:
        offers_query = offers_query.with_for_update()
    offers = {o.product_id:o for o in db.scalars(offers_query)}
    result=[]; currencies=set(); total=Decimal('0')
    for item in items:
        product, offer = products.get(item.product_id), offers.get(item.product_id)
        if not product or not offer or not offer.is_active:
            raise HTTPException(409, f'商品 #{item.product_id} 已下架或尚未设置销售价格')
        if offer.stock < item.quantity:
            raise HTTPException(409, f'{product.name_zh or product.name_original} 库存不足（剩余 {offer.stock}）')
        image = db.scalar(select(ProductImage.asset_id).where(ProductImage.product_id == product.id)
                          .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id).limit(1))
        currencies.add(offer.currency); subtotal=offer.price*item.quantity; total+=subtotal
        result.append({'product_id':product.id,'name':product.name_zh or product.name_original,
                       'quantity':item.quantity,'unit_price':str(offer.price),'subtotal':str(subtotal),
                       'image_asset_id':image,'image':{'url':f'/api/catalog/media/{image}'} if image else None})
    if len(currencies) != 1:
        raise HTTPException(422, '不同币种的商品需要分别下单，请选择相同币种商品')
    if total > Decimal('999999999999.99'):
        raise HTTPException(422, '订单金额过大，请减少商品数量或拆分订单')
    return {'items':result,'total':str(total),'currency':next(iter(currencies)), 'shipping_fee':'0.00','demo':True}, offers


def order_data(db, order):
    items = db.scalars(select(ShopOrderItem).where(ShopOrderItem.order_id == order.id).order_by(ShopOrderItem.id)).all()
    result = {key:getattr(order,key) for key in ('id','number','status','currency','shipping_address','note','created_at',
             'expires_at','paid_at','shipped_at','completed_at','cancelled_at','cancel_reason','carrier','tracking_number','refunded_at')}
    result['aftersales']=latest_summary(db,order.id)
    result.update(total=str(order.total), demo=True, items=[{'product_id':item.product_id,'name':item.name,
          'quantity':item.quantity,'unit_price':str(item.unit_price),'subtotal':str(item.unit_price*item.quantity),
          'image':{'url':f'/api/catalog/media/{item.image_asset_id}'} if item.image_asset_id else None} for item in items])
    return result


def owned_order(db, user, order_id):
    order = db.scalar(select(ShopOrder).where(ShopOrder.id == order_id, ShopOrder.user_id == user.id).with_for_update())
    if order is None:
        raise HTTPException(404, '订单不存在')
    return order


@router.get('/addresses')
def addresses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {'items':[address_data(a) for a in db.scalars(select(ShippingAddress).where(ShippingAddress.user_id == user.id)
            .order_by(ShippingAddress.is_default.desc(), ShippingAddress.id))]}


def save_address(db, user, body, address=None):
    lock_user(db,user)
    existing=db.scalars(select(ShippingAddress).where(ShippingAddress.user_id == user.id).order_by(ShippingAddress.id)).all()
    if address is None and len(existing)>=20:
        raise HTTPException(422,'最多保存 20 个收货地址')
    make_default=body.is_default or not existing
    if address is not None and address.is_default:
        make_default=True
    if make_default:
        for entry in existing: entry.is_default=False
    if address is None:
        address=ShippingAddress(user_id=user.id); db.add(address)
    for key,value in body.model_dump().items(): setattr(address,key,value)
    address.is_default=make_default
    db.flush(); result=address_data(address); db.commit(); return result


@router.post('/addresses', status_code=201)
def add_address(body: AddressBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_address(db,user,body)


@router.put('/addresses/{address_id}')
def edit_address(address_id: int, body: AddressBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_user(db,user)
    return save_address(db,user,body,owned_address(db,user,address_id))


@router.delete('/addresses/{address_id}', status_code=204)
def delete_address(address_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_user(db,user); address=owned_address(db,user,address_id); was_default=address.is_default
    db.delete(address); db.flush()
    if was_default:
        other=db.scalar(select(ShippingAddress).where(ShippingAddress.user_id==user.id).order_by(ShippingAddress.id).limit(1))
        if other:other.is_default=True
    db.commit()


@router.get('/cart')
def cart(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expire_orders(db)
    rows=db.scalars(select(CartItem).where(CartItem.user_id==user.id).order_by(CartItem.id.desc())).all()
    ids=[item.product_id for item in rows]
    visible={p['id']:p for p in serialize_products(db,db.execute(product_query().where(Product.id.in_(ids))).all())}
    result={'items':[{'id':item.id,'product_id':item.product_id,'quantity':item.quantity,
                     'product':visible.get(item.product_id),'available':bool(visible.get(item.product_id) and
                      visible[item.product_id].get('offer',{}).get('is_active'))} for item in rows]}
    db.commit();return result


@router.post('/cart', status_code=201)
def add_cart(body: CartAdd, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_user(db,user)
    item=db.scalar(select(CartItem).where(CartItem.user_id==user.id,CartItem.product_id==body.product_id))
    quantity=body.quantity+(item.quantity if item else 0)
    if quantity>99:raise HTTPException(422,'同款商品最多加入 99 件')
    if item is None and db.scalar(select(func.count()).select_from(CartItem).where(CartItem.user_id==user.id))>=100:
        raise HTTPException(422,'购物车最多保存 100 款商品')
    quote(db,[Selection(product_id=body.product_id,quantity=quantity)])
    if item:item.quantity=quantity
    else:item=CartItem(user_id=user.id,product_id=body.product_id,quantity=quantity);db.add(item)
    db.flush();result={'id':item.id,'quantity':item.quantity};db.commit();return result


@router.patch('/cart/{item_id}')
def update_cart(item_id: int, body: CartUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_user(db,user)
    item=db.scalar(select(CartItem).where(CartItem.id==item_id,CartItem.user_id==user.id))
    if item is None:raise HTTPException(404,'购物车条目不存在')
    quote(db,[Selection(product_id=item.product_id,quantity=body.quantity)])
    item.quantity=body.quantity;db.commit();return {'quantity':body.quantity}


@router.delete('/cart/{item_id}', status_code=204)
def delete_cart(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_user(db,user)
    item=db.scalar(select(CartItem).where(CartItem.id==item_id,CartItem.user_id==user.id))
    if item is None:raise HTTPException(404,'购物车条目不存在')
    db.delete(item);db.commit()


@router.post('/checkout/preview')
def preview(body: PreviewBody, db: Session = Depends(get_db)):
    expire_orders(db)
    result,_=quote(db,body.items);db.commit();return result


@router.post('/orders', status_code=201)
def checkout(body: CheckoutBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expire_orders(db);lock_user(db,user)
    fingerprint=hashlib.sha256(json.dumps(body.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
    previous=db.scalar(select(ShopOrder).where(ShopOrder.user_id==user.id,ShopOrder.request_key==body.request_key))
    if previous:
        if previous.request_hash!=fingerprint:raise HTTPException(409,'重复请求编号对应不同订单，请刷新结算页面')
        result=order_data(db,previous);db.commit();return result
    address=owned_address(db,user,body.address_id)
    cart_entries=[]
    if body.cart_item_ids:
        cart_entries=db.scalars(select(CartItem).where(CartItem.user_id==user.id,CartItem.id.in_(body.cart_item_ids)).with_for_update()).all()
        actual={entry.product_id:entry.quantity for entry in cart_entries}
        if len(cart_entries)!=len(body.cart_item_ids) or actual!={i.product_id:i.quantity for i in body.items}:
            raise HTTPException(409,'购物车已变化，请返回购物车重新结算')
    result,offers=quote(db,body.items,lock=True)
    for item in body.items:
        offer=offers[item.product_id]
        if item.expected_price!=offer.price or item.currency!=offer.currency:
            raise HTTPException(409,'商品价格已变化，请重新加载结算页面确认')
    order=ShopOrder(number='S'+now().strftime('%Y%m%d%H%M%S')+uuid4().hex[:10],user_id=user.id,
                    request_key=body.request_key,request_hash=fingerprint,status='pending_payment',
                    total=Decimal(result['total']),currency=result['currency'],shipping_address={k:v for k,v in address_data(address).items() if k not in ('id','is_default')},
                    note=body.note,expires_at=now()+timedelta(minutes=30))
    db.add(order);db.flush()
    for item in result['items']:
        offers[item['product_id']].stock-=item['quantity'];offers[item['product_id']].updated_at=now()
        db.add(ShopOrderItem(order_id=order.id,product_id=item['product_id'],name=item['name'],
               image_asset_id=item['image_asset_id'],quantity=item['quantity'],unit_price=Decimal(item['unit_price'])))
    for entry in cart_entries:db.delete(entry)
    db.flush();response=order_data(db,order);db.commit();return response


@router.get('/orders')
def orders(status: str = Query('',pattern='^(|pending_payment|paid|shipped|completed|cancelled|refunded)$'),
           page: int = Query(1,ge=1),db: Session = Depends(get_db),user: User = Depends(get_current_user)):
    expire_orders(db)
    query=select(ShopOrder).where(ShopOrder.user_id==user.id)
    if status:query=query.where(ShopOrder.status==status)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    data=db.scalars(query.order_by(ShopOrder.id.desc()).offset((page-1)*10).limit(10)).all()
    result={'items':[order_data(db,o) for o in data],'total':total,'total_pages':(total+9)//10}
    db.commit();return result


@router.get('/orders/{order_id}')
def detail(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expire_orders(db);result=order_data(db,owned_order(db,user,order_id));db.commit();return result


def transition(order_id: int, action: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if action not in ('pay','cancel','complete'):raise HTTPException(404,'操作不存在')
    expire_orders(db);order=owned_order(db,user,order_id)
    if action=='pay':
        if order.status=='paid':pass
        elif order.status!='pending_payment':raise HTTPException(409,'当前订单不可支付')
        elif order.expires_at<=now():raise HTTPException(409,'订单已超时，请刷新后重新下单')
        else:order.status='paid';order.paid_at=now()
    elif action=='cancel':
        if order.status=='cancelled':pass
        elif order.status!='pending_payment':raise HTTPException(409,'仅待支付订单可以取消，其他售后请联系客服')
        else:
            release_stock(db,[order]);order.status='cancelled';order.cancelled_at=now();order.cancel_reason='用户取消'
    else:
        if active_refund(db,order.id):raise HTTPException(409,'售后处理中，暂不能确认收货')
        if order.status=='completed':pass
        elif order.status!='shipped':raise HTTPException(409,'仅已发货订单可以确认收货')
        else:order.status='completed';order.completed_at=now()
    db.flush();result=order_data(db,order);db.commit();return result


@router.post('/orders/{order_id}/pay')
def pay(order_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    return transition(order_id,'pay',db,user)


@router.post('/orders/{order_id}/cancel')
def cancel(order_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    return transition(order_id,'cancel',db,user)


@router.post('/orders/{order_id}/complete')
def confirm_receipt(order_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    return transition(order_id,'complete',db,user)


@admin_router.get('/offers/{product_id}')
def get_offer(product_id: int, db: Session = Depends(get_db)):
    offer=db.get(SaleOffer,product_id)
    return {'offer':{key:getattr(offer,key) for key in ('price','currency','stock','is_active','updated_at')} if offer else None,'demo':True}


@admin_router.put('/offers/{product_id}')
def set_offer(product_id: int,body: OfferBody,db: Session = Depends(get_db)):
    product=db.scalar(select(Product).where(Product.id==product_id,Product.status.in_(VISIBLE_STATUSES)).with_for_update(read=True))
    if product is None:raise HTTPException(404,'商品不存在或已删除')
    offer=db.scalar(select(SaleOffer).where(SaleOffer.product_id==product_id).with_for_update())
    if (offer and body.updated_at!=offer.updated_at) or (not offer and body.updated_at is not None):
        raise HTTPException(409,'库存或售价已变化，请重新加载销售设置')
    if offer is None:offer=SaleOffer(product_id=product_id);db.add(offer)
    for key in ('price','currency','stock','is_active'):setattr(offer,key,getattr(body,key))
    offer.updated_at=now();db.flush();result=get_offer(product_id,db);db.commit();return result


@admin_router.get('/orders')
def admin_orders(status: str = Query('',pattern='^(|pending_payment|paid|shipped|completed|cancelled|refunded)$'),
                 q: str = Query('',max_length=40),page: int = Query(1,ge=1),db: Session = Depends(get_db)):
    expire_orders(db);query=select(ShopOrder)
    if status:query=query.where(ShopOrder.status==status)
    if q.strip():query=query.where(ShopOrder.number.icontains(q.strip(),autoescape=True))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    data=db.scalars(query.order_by(ShopOrder.id.desc()).offset((page-1)*10).limit(10)).all()
    result={'items':[{**order_data(db,o),'user_id':o.user_id} for o in data],'total':total,'total_pages':(total+9)//10}
    db.commit();return result


@admin_router.post('/orders/{order_id}/ship')
def ship(order_id: int,body: ShippingBody,db: Session = Depends(get_db)):
    order=db.scalar(select(ShopOrder).where(ShopOrder.id==order_id).with_for_update())
    if order is None:raise HTTPException(404,'订单不存在')
    if order.status!='paid':raise HTTPException(409,'仅已支付订单可以发货')
    if active_refund(db,order.id):raise HTTPException(409,'退款审核或退货处理中，不能发货')
    if not body.carrier.strip():raise HTTPException(422,'快递公司不能为空')
    order.status='shipped';order.carrier=body.carrier.strip();order.tracking_number=body.tracking_number;order.shipped_at=now()
    for reminder in db.scalars(select(ShipmentReminder).where(ShipmentReminder.order_id==order.id,ShipmentReminder.status=='pending')):
        reminder.status='handled';reminder.handled_note='订单已发货';reminder.handled_at=now()
    db.flush();result=order_data(db,order);db.commit();return result
