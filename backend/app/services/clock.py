"""业务服务共用的 UTC 时间函数。"""

from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)
