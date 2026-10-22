"""纯规则：退款政策、原因编码与自动退款条件，不访问数据库。"""

from datetime import timedelta
from .clock import now

ACTIVE_REFUNDS = ("review_pending", "awaiting_return", "return_in_transit")
REASONS = {
    "not_needed": "不想要了",
    "wrong_order": "拍错商品",
    "change_mind": "改变主意",
    "not_received": "物流异常/未收到货",
    "quality": "质量问题",
    "damaged": "商品破损",
    "payment_issue": "支付异常",
    "other": "其他原因",
}


def refund_policy():
    return {
        "demo": True,
        "version": "demo-v1",
        "scope": "整单全额模拟退款，不发生真实资金转账",
        "auto_rule": "已支付未发货，支付后24小时内，未收到货，原因是不想要、拍错或改变主意：自动全额模拟退款。",
        "manual_rule": "已发货、已收货、支付超过24小时，或质量/破损/支付异常/其他情况：人工审核。",
        "return_rule": "已收到货的已发货/已完成订单：人工批准后提供退货地址，用户填写退货快递单号，客服验收后退款。未收到货的物流争议由客服核实后处理。",
        "timing": "已收货7天内优先按常规售后处理，超过7天仍可提交人工评估；这不是自动拒绝条件。退货批准后建议7天内寄出。",
        "required": ["退款原因", "至少10字情况说明", "确认联系电话", "是否收到货"],
        "evidence_rule": "质量或破损必须上传至少1张、最多3张照片；其他原因照片可选。每张最多5MB。无需银行卡、验证码或账户密码。",
        "reasons": [
            {
                "code": code,
                "label": label,
                "requires_evidence": code in ("quality", "damaged"),
            }
            for code, label in REASONS.items()
        ],
    }


def auto_route(order, reason, received):
    # 自动退款条件由代码判定：已支付未发货、支付后 24 小时内、普通撤单原因且未收货。
    # 不满足条件的申请转人工审核，不由模型决定是否退款。
    return (
        order.status == "paid"
        and order.paid_at is not None
        and timedelta(0) <= now() - order.paid_at <= timedelta(hours=24)
        and reason in ("not_needed", "wrong_order", "change_mind")
        and not received
    )
