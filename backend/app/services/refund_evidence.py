"""私有售后凭证：文件校验、保存、归属检查与安全路径解析。

存储根路径由调用方传入；服务返回路径，HTTP 文件响应由 API 创建。
"""

import base64
import binascii
from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from app.database.aftersales_models import RefundEvidence
from .clock import now
from .order_access import owned


def upload_evidence(order_id, body, db, user, materials_root):
    order = owned(db, user, order_id)
    if order.status not in ("paid", "shipped", "completed"):
        raise HTTPException(409, "该订单当前不可上传退款凭证")
    count = db.scalar(
        select(func.count())
        .select_from(RefundEvidence)
        .where(
            RefundEvidence.user_id == user.id,
            RefundEvidence.created_at >= now() - timedelta(days=1),
        )
    )
    if count >= 30:
        raise HTTPException(429, "今天上传凭证较多，请稍后再试")
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
            output = BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=90)
        data = output.getvalue()
    except (
        ValueError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            422, "请选择5MB内有效JPEG、PNG或WebP图片（最多2000万像素）"
        ) from None
    key = f"private_refund_evidence/{uuid4().hex}.jpg"
    path = materials_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    entry = RefundEvidence(user_id=user.id, order_id=order.id, storage_key=key)
    db.add(entry)
    db.flush()
    result = {"id": entry.id, "url": f"/api/shop/refund-evidence/{entry.id}"}
    db.commit()
    return result


def evidence_file(evidence_id, db, user, materials_root):
    evidence = db.get(RefundEvidence, evidence_id)
    if evidence is None or not (
        evidence.user_id == user.id
        or (user.role == "super_admin" and evidence.refund_id is not None)
    ):
        raise HTTPException(404, "凭证不存在")
    path = (materials_root / evidence.storage_key).resolve()
    if (
        not path.is_relative_to(materials_root / "private_refund_evidence")
        or not path.is_file()
    ):
        raise HTTPException(404, "凭证文件不存在")
    return path
