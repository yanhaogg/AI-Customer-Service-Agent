"""商品图片和私有凭证的根路径配置，不依赖 API。"""

import os
from pathlib import Path

MATERIALS_ROOT = Path(
    os.getenv("PRODUCT_MATERIALS_ROOT")
    or Path(__file__).resolve().parents[2] / "product_materials"
).resolve()
VISIBLE_STATUSES = ("draft", "reviewed", "published")
