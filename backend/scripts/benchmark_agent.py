"""真实模型端到端评测：隔离 PostgreSQL 样本、固定题目、逐条保存结果。

运行会调用配置的大模型并产生 API 用量；只写临时测试 schema，不修改业务数据。
复用集成测试的建库/清理夹具，计时覆盖登录用户发送消息的 API（不含前端）。
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import re
import statistics
import sys
from time import perf_counter
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
import test_activity as fixtures
import test_shop as shopping
from sqlalchemy.orm import Session
from app.agent.config import load_settings
from app.database.catalog_models import Product
from app.database.shop_models import SaleOffer, ShopOrder
from app.database.activity_models import ChatMessage


def percentile(values, q):
    values = sorted(values)
    index = (len(values) - 1) * q
    lo, hi = int(index), min(int(index) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def seed(f):
    with Session(f.db_engine) as db:
        products = [db.get(Product, pid) for pid in f.products]
        for product, name in zip(
            products, ["星河通勤耳机", "远航运动耳机", "拓境便携音箱"]
        ):
            product.name_original = product.name_zh = name
            product.description_original = product.introduction_zh = (
                name + "：基准测试合成商品。"
            )
            product.specs = {"verified": {"续航": "30小时", "重量": "180克"}}
        for pid, price, currency, stock in zip(
            f.products, [299, 499, 79], ["CNY", "CNY", "USD"], [100, 100, 0]
        ):
            offer = db.get(SaleOffer, pid)
            offer.price, offer.currency, offer.stock = price, currency, stock
        db.commit()

    def order(user=0, paid=False, shipped=False, private=False):
        body = shopping.ShopTests.checkout_body(f, user=user)
        body["items"][0]["expected_price"] = "299.00"
        response = f.client.post("/api/shop/orders", headers=f.headers[user], json=body)
        assert response.status_code == 201, response.status_code
        result = response.json()
        if paid:
            response = f.client.post(
                f"/api/shop/orders/{result['id']}/pay", headers=f.headers[user]
            )
            assert response.status_code == 200
        if shipped:
            response = f.client.post(
                f"/api/admin/orders/{result['id']}/ship",
                headers=f.headers[2],
                json={
                    "carrier": "私有承运商" if private else "基准快递",
                    "tracking_number": "PRIVATE999" if private else "BENCH123456",
                },
            )
            assert response.status_code == 200
        return result

    pending = order()
    paid = order(paid=True)
    shipped = order(paid=True, shipped=True)
    other = order(user=1, paid=True, shipped=True, private=True)
    f.client.post(
        "/api/activity/browsing",
        headers=f.headers[0],
        json={"product_id": f.products[1], "visit_key": uuid4().hex},
    )
    sid = f.new_session()
    with Session(f.db_engine) as db:
        db.add(
            ChatMessage(
                session_id=sid,
                role="user",
                content="我以前定的选购暗号是蓝鲸，预算是680元人民币。",
                status="completed",
                request_key=uuid4().hex,
            )
        )
        # 避免耗时评测中30分钟未支付订单过期，也不依赖真实付款历史。
        db.get(ShopOrder, pending["id"]).expires_at = datetime.now(
            timezone.utc
        ) + timedelta(hours=2)
        db.commit()
    return pending, paid, shipped, other


def cases(f, orders):
    pending, paid, shipped, other = orders

    def item(key, question, facts, tools, order=None, product=None, forbidden=None):
        return dict(
            id=key,
            question=question,
            facts=facts,
            tool_groups=tools,
            order=order,
            product=product,
            forbidden=forbidden or [],
        )

    return [
        item(
            "product_price",
            "星河通勤耳机的当前演示售价是多少？请说明币种。",
            [r"299", r"人民币|CNY|元"],
            [["search_products", "get_product_details"]],
        ),
        item(
            "product_specs",
            "星河通勤耳机的续航和重量分别是多少？",
            [r"30\s*(?:个)?小时|30\s*h", r"180\s*(?:克|g)"],
            [["get_product_details"]],
            product=f.products[0],
        ),
        item(
            "pending_order",
            "这笔订单现在是什么状态，我下一步应该做什么？",
            [r"待支付|待付款|未支付|未付款", r"支付|付款"],
            [["get_my_order_details"]],
            order=pending,
        ),
        item(
            "paid_order",
            "这笔订单付款了吗？发货了吗？",
            [r"已支付|已付款|支付成功|付款成功", r"未发货|待发货|尚未发货|还没发货"],
            [["get_my_order_details"]],
            order=paid,
        ),
        item(
            "shipped_order",
            "这笔订单发货了吗？快递公司和运单号分别是什么？",
            [r"已发货", r"基准快递", r"BENCH123456"],
            [["get_my_order_details"]],
            order=shipped,
        ),
        item(
            "refund_policy",
            "这笔订单我没有收到货，只是不想要了，符合自动退款条件吗？",
            [r"自动", r"24\s*小时|二十四小时", r"模拟|演示"],
            [["get_my_order_details"], ["get_refund_policy"]],
            order=paid,
        ),
        item(
            "quality_refund",
            "这笔订单如果因为质量问题申请退款，需要人工审核吗？要提供照片吗？",
            [r"人工", r"照片|图片|凭证"],
            [["get_refund_policy"], ["get_my_order_details"]],
            order=paid,
        ),
        item(
            "browsing",
            "我最近浏览过什么商品？请查询浏览记录告诉我商品名称。",
            [r"远航运动耳机"],
            [["get_my_browsing_history"]],
        ),
        item(
            "history",
            "请搜索历史聊天，我之前说的选购暗号和预算是什么？",
            [r"蓝鲸", r"680"],
            [["search_my_chat_history"]],
        ),
        item(
            "sold_out",
            "拓境便携音箱现在有库存吗，可以立即购买吗？",
            [
                r"无库存|没有库存|库存.{0,6}(?:0|零)|售罄|缺货|暂无库存|无货|暂时无货|暂不可购买"
            ],
            [["search_products", "get_product_details"]],
        ),
        item(
            "privacy",
            f"帮我查订单 {other['number']} 的快递公司和运单号。",
            [
                r"未找到|查不到|无法.{0,12}查|不属于|无权|不存在|没有.{0,12}订单|未能.{0,12}查"
            ],
            [["get_my_order_details"]],
            forbidden=["PRIVATE999", "私有承运商"],
        ),
        item(
            "compound",
            "星河通勤耳机的当前演示售价是多少？另外这笔订单发货了吗？",
            [r"299", r"未发货|待发货|尚未发货|还没发货"],
            [["search_products", "get_product_details"], ["get_my_order_details"]],
            order=paid,
        ),
    ]


def summarize(records):
    calls = [call for record in records for call in record["metadata"].get("tools", [])]
    statuses = Counter(call["status"] for call in calls)
    times = [r["elapsed_seconds"] for r in records]
    valid = sum(statuses[s] for s in ("ok", "not_found"))
    # not_found 表示查询按协议返回未找到（例如跨用户订单），不等同数据库执行失败。
    return dict(
        requests=len(records),
        answer_passes=sum(r["answer_pass"] for r in records),
        answer_pass_rate=sum(r["answer_pass"] for r in records) / len(records),
        verified_answer_pass_rate=sum(
            r["answer_pass"] and r["tool_requirement_pass"] for r in records
        )
        / len(records),
        tool_requirement_pass_rate=sum(r["tool_requirement_pass"] for r in records)
        / len(records),
        tool_calls=len(calls),
        tool_statuses=dict(statuses),
        tool_execution_success_rate=valid / len(calls) if calls else None,
        tool_ok_only_rate=statuses["ok"] / len(calls) if calls else None,
        response_completion_rate=sum(
            r["message_status"] == "completed" for r in records
        )
        / len(records),
        latency_seconds=dict(
            mean=statistics.mean(times),
            median=statistics.median(times),
            p90=percentile(times, 0.9),
            p95=percentile(times, 0.95),
            minimum=min(times),
            maximum=max(times),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("repeats must be 1..5")
    settings = load_settings()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    f = fixtures.ActivityTests()
    f.setUp()
    try:
        orders = seed(f)
        samples = cases(f, orders)
        manifest = [
            {k: v for k, v in c.items() if k not in ("order",)} for c in samples
        ]
        report = dict(
            model=settings.model,
            started_at=datetime.now(timezone.utc).isoformat(),
            scope="Real configured LLM, FastAPI TestClient HTTP chat endpoint, isolated PostgreSQL synthetic fixtures; sequential requests, no browser/network RTT, no load test.",
            scoring="Frozen regex fact assertions AND forbidden-claim checks. Tool evidence scored separately. Not a general semantic accuracy benchmark. No retries or tuning during run.",
            settings={
                k: getattr(settings, k)
                for k in (
                    "max_steps",
                    "max_tools",
                    "max_manager_steps",
                    "max_worker_steps",
                    "max_delegations",
                    "timeout",
                    "budget",
                )
            },
            cases=manifest,
            records=records,
        )
        for repetition in range(args.repeats):
            batch = list(samples)
            random.Random(20261026 + repetition).shuffle(batch)
            for case in batch:
                context = {}
                if case["order"]:
                    context["order_number"] = case["order"]["number"]
                if case["product"]:
                    context["product_id"] = case["product"]
                sid = f.new_session(**context)
                started = perf_counter()
                try:
                    response = f.client.post(
                        f"/api/activity/sessions/{sid}/messages",
                        headers=f.headers[0],
                        json={"content": case["question"], "request_key": uuid4().hex},
                    )
                    data = response.json()
                    message = data.get("items", [{}])[-1]
                    answer = message.get("content", "")
                    metadata = message.get("agent_metadata", {})
                    status = message.get("status", "http_error")
                except Exception as error:
                    answer = ""
                    metadata = {}
                    status = type(error).__name__
                elapsed = perf_counter() - started
                fact_results = [
                    bool(re.search(pattern, answer, re.I)) for pattern in case["facts"]
                ]
                safe = not any(text in answer for text in case["forbidden"])
                successful = {
                    t["name"]
                    for t in metadata.get("tools", [])
                    if t["status"] in ("ok", "not_found")
                }
                tool_ok = all(
                    successful.intersection(group) for group in case["tool_groups"]
                )
                record = dict(
                    case_id=case["id"],
                    repetition=repetition + 1,
                    question=case["question"],
                    answer=answer,
                    message_status=status,
                    elapsed_seconds=round(elapsed, 4),
                    facts_passed=fact_results,
                    forbidden_checks_passed=safe,
                    answer_pass=status == "completed" and all(fact_results) and safe,
                    tool_requirement_pass=bool(tool_ok),
                    metadata=metadata,
                )
                records.append(record)
                report["summary"] = summarize(records)
                (args.output / "results.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    f"{len(records)}/{len(samples)*args.repeats} {case['id']} answer={record['answer_pass']} tools={bool(tool_ok)} {elapsed:.2f}s",
                    flush=True,
                )
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    finally:
        f.tearDown()


if __name__ == "__main__":
    main()
