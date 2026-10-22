"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin
from app.database.session import get_db
from app.schemas.admin_products import ProductWrite, ImageUpload
from app.services import product_management as product_management_service
from app.services import product_media as product_media_service

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-products"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("/product-categories")
def categories(db: Session = Depends(get_db)):
    return product_management_service.categories(db)


@router.get("/products")
def products(
    q: str = Query("", max_length=150),
    category_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
):
    return product_management_service.products(q, category_id, page, page_size, db)


@router.get("/products/{product_id}")
def detail(product_id: int, db: Session = Depends(get_db)):
    return product_management_service.detail(product_id, db)


@router.post("/products", status_code=201)
def create(body: ProductWrite, db: Session = Depends(get_db)):
    return product_management_service.create(body, db)


@router.put("/products/{product_id}")
def update(product_id: int, body: ProductWrite, db: Session = Depends(get_db)):
    return product_management_service.update(product_id, body, db)


@router.delete("/products/{product_id}", status_code=204)
def remove(product_id: int, db: Session = Depends(get_db)):
    return product_management_service.remove(product_id, db)


@router.post("/product-images", status_code=201)
def upload(body: ImageUpload, db: Session = Depends(get_db)):
    return product_media_service.upload(body, db)
