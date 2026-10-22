"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services import homepage as homepage_service
from app.services import catalog as catalog_service

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    return catalog_service.categories(db)


@router.get("/products")
def products(
    category: str | None = None,
    q: str = Query("", max_length=150),
    sort: str = Query("recommended", pattern="^(recommended|price_asc|price_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
):
    return catalog_service.products(category, q, sort, page, page_size, db)


@router.get("/home")
def home(db: Session = Depends(get_db)):
    return homepage_service.home(db)


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    return catalog_service.product_detail(product_id, db)


@router.get("/media/{asset_id}")
def media(asset_id: int, db: Session = Depends(get_db)):
    path, content_type = catalog_service.media(asset_id, db)
    return FileResponse(path, media_type=content_type)
