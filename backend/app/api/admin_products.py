"""Superadmin-only catalog writes. Deletion archives records and retains source evidence."""
import base64
import binascii
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import require_superadmin
from app.api.catalog import MATERIALS_ROOT, VISIBLE_STATUSES, serialize_products
from app.database.catalog_models import CatalogCategory, MediaAsset, Product, ProductImage, ProductPriceRecord, ProductSource
from app.database.homepage_models import HomepageConfig
from app.database.session import get_db

router = APIRouter(prefix='/api/admin', tags=['admin-products'], dependencies=[Depends(require_superadmin)])
PositiveId = Annotated[StrictInt, Field(gt=0)]


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category_id: PositiveId
    name_original: str = Field(min_length=1, max_length=500)
    name_zh: str = Field(default='', max_length=500)
    brand: str = Field(default='', max_length=200)
    model: str = Field(default='', max_length=200)
    description_original: str = Field(min_length=1, max_length=30000)
    introduction_zh: str = Field(min_length=1, max_length=10000)
    specs: dict[str, str] = Field(default_factory=dict, max_length=100)
    image_asset_id: PositiveId | None = None
    price_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price_currency: str = Field(default='USD', pattern='^(USD|CNY|EUR|GBP|JPY|HKD)$')
    updated_at: datetime | None = None

    @field_validator('name_original', 'description_original', 'introduction_zh')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('必填字段不能为空')
        return value.strip()

    @field_validator('specs')
    @classmethod
    def limited_specs(cls, value):
        if any(not key.strip() or len(key) > 100 or len(item) > 2000 for key, item in value.items()):
            raise ValueError('参数名称限 100 字，参数值限 2000 字')
        return value


class ImageUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data: str = Field(max_length=8_000_000)


def editable_product(db, product_id, lock=False):
    query = select(Product).where(Product.id == product_id, Product.status != 'deleted')
    if lock:
        query = query.with_for_update()
    product = db.scalar(query)
    if product is None:
        raise HTTPException(404, '商品不存在或已删除')
    return product


def product_data(db, product):
    category = db.get(CatalogCategory, product.category_id)
    result = serialize_products(db, [(product, category)])[0]
    result.update(category_id=product.category_id, name_zh=product.name_zh or '',
                  description_original=product.description_original, introduction_zh=product.introduction_zh,
                  specs=(product.specs or {}).get('verified', {}), updated_at=product.updated_at,
                  image_asset_id=db.scalar(select(ProductImage.asset_id).where(ProductImage.product_id == product.id)
                      .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id).limit(1)))
    return result


@router.get('/product-categories')
def categories(db: Session = Depends(get_db)):
    return {'items': [{'id': row.id, 'name': row.name, 'code': row.code}
                      for row in db.scalars(select(CatalogCategory).order_by(CatalogCategory.code))]}


@router.get('/products')
def products(q: str = Query('', max_length=150), category_id: int | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=60), db: Session = Depends(get_db)):
    query = select(Product, CatalogCategory).join(CatalogCategory, Product.category_id == CatalogCategory.id).where(Product.status != 'deleted')
    if category_id:
        query = query.where(Product.category_id == category_id)
    if q.strip():
        query = query.where(or_(*[column.icontains(q.strip(), autoescape=True) for column in
                                  (Product.name_original, Product.name_zh, Product.brand, Product.model)]))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Product.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items': serialize_products(db, rows), 'total': total, 'total_pages': (total+page_size-1)//page_size}


@router.get('/products/{product_id}')
def detail(product_id: int, db: Session = Depends(get_db)):
    return product_data(db, editable_product(db, product_id))


def apply_changes(db, product, body):
    if db.get(CatalogCategory, body.category_id) is None:
        raise HTTPException(422, '分类不存在')
    if body.image_asset_id is not None and db.get(MediaAsset, body.image_asset_id) is None:
        raise HTTPException(422, '图片不存在，请重新上传或选择')
    for field in ('category_id', 'name_original', 'name_zh', 'brand', 'model', 'description_original', 'introduction_zh'):
        setattr(product, field, getattr(body, field))
    # Preserve imported source/extracted evidence; administrators edit verified parameters only.
    product.specs = {**(product.specs or {}), 'verified': body.specs}
    product.updated_at = datetime.now(timezone.utc)
    db.flush()
    source = db.scalar(select(ProductSource).where(ProductSource.product_id == product.id, ProductSource.source_name == 'admin'))
    if source is None:
        source = ProductSource(product_id=product.id, source_name='admin', source_sku=product.import_key,
                               collected_at=datetime.now(timezone.utc), raw_data={})
        db.add(source)
        db.flush()
    current_image = db.scalar(select(ProductImage).where(ProductImage.product_id == product.id)
                              .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id).limit(1))
    if (current_image.asset_id if current_image else None) != body.image_asset_id:
        # Historical image rows are retained; only the primary flag is changed.
        for image in db.scalars(select(ProductImage).where(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True))):
            image.is_primary = False
        db.flush()
        if body.image_asset_id is not None:
            image = db.scalar(select(ProductImage).where(ProductImage.product_id == product.id,
                              ProductImage.source_id == source.id, ProductImage.asset_id == body.image_asset_id))
            if image is None:
                image = ProductImage(product_id=product.id, source_id=source.id, asset_id=body.image_asset_id,
                                     sort_order=0, rights_status='admin_provided', original_metadata={})
                db.add(image)
            image.is_primary = True
            image.alt = product.name_zh or product.name_original
        else:
            # Removing an image explicitly removes product associations, never shared assets/files.
            from sqlalchemy import delete
            db.execute(delete(ProductImage).where(ProductImage.product_id == product.id))
    latest = db.scalar(select(ProductPriceRecord).where(ProductPriceRecord.product_id == product.id)
                       .order_by(ProductPriceRecord.collected_at.desc(), ProductPriceRecord.id.desc()).limit(1))
    if body.price_amount is None:
        if latest is not None:
            raise HTTPException(422, '已有参考价格不可清空，请填写新价格；历史价格记录将保留')
    elif latest is None or latest.amount != body.price_amount or latest.currency != body.price_currency:
        db.add(ProductPriceRecord(product_id=product.id, source_id=source.id, record_key=uuid4().hex,
                                  amount=body.price_amount, currency=body.price_currency, price_kind='admin_reference_price',
                                  collected_at=datetime.now(timezone.utc), current_price_verified=False))


@router.post('/products', status_code=201)
def create(body: ProductWrite, db: Session = Depends(get_db)):
    try:
        product = Product(import_key='admin:'+uuid4().hex, status='published')
        db.add(product)
        # Assign required fields before the first flush.
        with db.no_autoflush:
            apply_changes(db, product, body)
        db.flush()
        result = product_data(db, product)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.put('/products/{product_id}')
def update(product_id: int, body: ProductWrite, db: Session = Depends(get_db)):
    try:
        product = editable_product(db, product_id, lock=True)
        if body.updated_at is None or body.updated_at != product.updated_at:
            raise HTTPException(409, '商品已被其他页面修改，请重新加载后编辑')
        apply_changes(db, product, body)
        db.flush()
        result = product_data(db, product)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.delete('/products/{product_id}', status_code=204)
def remove(product_id: int, db: Session = Depends(get_db)):
    try:
        # Same lock order as homepage writes avoids a stale config resurrecting deleted selections.
        db.execute(text('SELECT pg_advisory_xact_lock(734120402)'))
        product = editable_product(db, product_id, lock=True)
        config = db.get(HomepageConfig, 1)
        if config and product_id in [config.hero_product_id, *config.spotlight_ids, *config.featured_ids]:
            config.spotlight_ids = [i for i in config.spotlight_ids if i != product_id]
            config.featured_ids = [i for i in config.featured_ids if i != product_id]
            if config.hero_product_id == product_id:
                replacement = db.scalar(select(Product.id).where(Product.id != product_id,
                    Product.status.in_(VISIBLE_STATUSES)).order_by(Product.id).limit(1))
                if replacement is None:
                    db.delete(config)
                else:
                    config.hero_product_id = replacement
                    config.spotlight_ids = [i for i in config.spotlight_ids if i != replacement]
                    config.featured_ids = [i for i in config.featured_ids if i != replacement]
            config.revision += 1
            config.updated_at = datetime.now(timezone.utc)
        product.status = 'deleted'
        product.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.post('/product-images', status_code=201)
def upload(body: ImageUpload, db: Session = Depends(get_db)):
    try:
        raw = base64.b64decode(body.data, validate=True)
        if not raw or len(raw) > 5_000_000:
            raise ValueError()
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 20_000_000:
                raise ValueError()
            image.load()
            # Normalize image bytes; discard embedded metadata and never serve uploaded SVG/HTML.
            output = BytesIO()
            image.convert('RGB').save(output, format='JPEG', quality=90)
            width, height = image.size
        data = output.getvalue()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, '请选择 5MB 以内的有效 JPEG、PNG 或 WebP 图片（最多 2000 万像素）') from None
    digest = hashlib.sha256(data).hexdigest()
    # Serialize identical uploads so the asset hash remains unique.
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(digest[:15], 16)})
    asset = db.scalar(select(MediaAsset).where(MediaAsset.sha256 == digest))
    if asset is None:
        key = f'admin_uploads/{digest}.jpg'
        path = MATERIALS_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        asset = MediaAsset(storage_key=key, sha256=digest, width=width, height=height,
                           byte_size=len(data), content_type='image/jpeg')
        db.add(asset)
        db.flush()
    result = {'asset_id': asset.id, 'url': f'/api/catalog/media/{asset.id}'}
    db.commit()
    return result
