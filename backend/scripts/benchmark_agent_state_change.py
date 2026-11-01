"""补充时效性评测：同一会话先问一次，修改隔离样本，再重复提问。

2条预热请求不计入评分；商品价格和订单状态变化后，各问2次，共4条评分请求。
不会修改 Agent 代码或提示词。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from time import perf_counter
from uuid import uuid4

import benchmark_agent as benchmark
from sqlalchemy.orm import Session
from app.database.shop_models import SaleOffer


def ask(f, sid, case, repetition):
    start = perf_counter()
    response = f.client.post(
        f"/api/activity/sessions/{sid}/messages",
        headers=f.headers[0],
        json={"content": case["question"], "request_key": uuid4().hex},
    )
    message = response.json().get("items", [{}])[-1]
    elapsed = perf_counter() - start
    answer = message.get("content", "")
    metadata = message.get("agent_metadata", {})
    facts = [bool(re.search(pattern, answer, re.I)) for pattern in case["facts"]]
    successful = {
        t["name"]
        for t in metadata.get("tools", [])
        if t["status"] in ("ok", "not_found")
    }
    tools = all(successful.intersection(group) for group in case["tool_groups"])
    return dict(
        case_id=case["id"],
        repetition=repetition,
        question=case["question"],
        answer=answer,
        message_status=message.get("status", "http_error"),
        elapsed_seconds=round(elapsed, 4),
        facts_passed=facts,
        forbidden_checks_passed=True,
        answer_pass=message.get("status") == "completed" and all(facts),
        tool_requirement_pass=bool(tools),
        metadata=metadata,
    )


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    f = benchmark.fixtures.ActivityTests()
    f.setUp()
    try:
        orders = benchmark.seed(f)
        price = benchmark.cases(f, orders)[0]
        order = benchmark.cases(f, orders)[3]
        sessions = {
            price["id"]: f.new_session(),
            order["id"]: f.new_session(order_number=orders[1]["number"]),
        }
        warmups = [ask(f, sessions[c["id"]], c, 0) for c in (price, order)]
        print("2 warmups complete", flush=True)
        with Session(f.db_engine) as db:
            db.get(SaleOffer, f.products[0]).price = 349
            db.commit()
        response = f.client.post(
            f"/api/admin/orders/{orders[1]['id']}/ship",
            headers=f.headers[2],
            json={"carrier": "变更快递", "tracking_number": "CHANGE888"},
        )
        assert response.status_code == 200
        price["facts"] = [r"349", r"人民币|CNY|元"]
        order["facts"] = [r"已支付|已付款|支付成功|付款成功", r"已发货"]
        report = dict(
            model=benchmark.load_settings().model,
            started_at=datetime.now(timezone.utc).isoformat(),
            scope="Synthetic state-change followups in same sessions. Price 299→349 CNY; order paid→shipped. Two warmups excluded; four scored followups.",
            warmups=warmups,
            cases=[
                {k: v for k, v in c.items() if k not in ("order",)}
                for c in (price, order)
            ],
            records=[],
        )
        for repetition in (1, 2):
            for case in (price, order):
                record = ask(f, sessions[case["id"]], case, repetition)
                report["records"].append(record)
                report["summary"] = benchmark.summarize(report["records"])
                (output / "results.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    f"{len(report['records'])}/4 {case['id']} fact={record['answer_pass']} tools={record['tool_requirement_pass']} {record['elapsed_seconds']}s",
                    flush=True,
                )
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    finally:
        f.tearDown()


if __name__ == "__main__":
    main()
