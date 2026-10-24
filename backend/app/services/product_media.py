"""后台商品图片校验与保存。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import base64
import binascii
import hashlib
from io import BytesIO
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from app.storage import MATERIALS_ROOT
from app.database.catalog_models import MediaAsset


def upload(body, db):
    """校验上传图片，标准化并按内容哈希复用资源。

    输入：
        body: ImageUpload：data，Base64 编码的图片字符串。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：asset_id、公开图片 url。

    流程：
        1. 严格解码 Base64
        2. 校验非空、最多 5MB、格式及 2000 万像素上限
        3. 转 RGB JPEG 去元数据
        4. 哈希并锁相同内容上传
        5. 复用资源或写文件及 MediaAsset
        6. flush、组装、提交；无效图片返回 422。
    """
    try:
        raw = base64.b64decode(body.data, validate=True)
        if not raw or len(raw) > 5_000_000:
            raise ValueError()
        with Image.open(BytesIO(raw)) as image:
            if (
                image.format not in ("JPEG", "PNG", "WEBP")
                or image.width * image.height > 20_000_000
            ):
                raise ValueError()
            image.load()
            # Normalize image bytes; discard embedded metadata and never serve uploaded SVG/HTML.
            output = BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=90)
            width, height = image.size
        data = output.getvalue()
    except (
        ValueError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            422, "请选择 5MB 以内的有效 JPEG、PNG 或 WebP 图片（最多 2000 万像素）"
        ) from None
    digest = hashlib.sha256(data).hexdigest()
    # Serialize identical uploads so the asset hash remains unique.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest[:15], 16)}
    )
    asset = db.scalar(select(MediaAsset).where(MediaAsset.sha256 == digest))
    if asset is None:
        key = f"admin_uploads/{digest}.jpg"
        path = MATERIALS_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        asset = MediaAsset(
            storage_key=key,
            sha256=digest,
            width=width,
            height=height,
            byte_size=len(data),
            content_type="image/jpeg",
        )
        db.add(asset)
        db.flush()
    result = {"asset_id": asset.id, "url": f"/api/catalog/media/{asset.id}"}
    db.commit()
    return result
