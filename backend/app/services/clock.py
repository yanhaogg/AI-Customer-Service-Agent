"""业务服务共用的 UTC 时间函数。"""

from datetime import datetime, timezone


def now():
    """提供业务服务统一使用的当前 UTC 时间。

    输入：
        无。

    输出：
        带 UTC 时区的 datetime 对象。

    流程：
        1. 调用 datetime.now(timezone.utc)；不访问数据库。
    """
    return datetime.now(timezone.utc)
