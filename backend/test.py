from app.agent.graph import app


result = app.invoke({

    "user_input":"我要退款",

    "order_id":"10001",

    "refund_amount":0,

    "refund_reason":"商品质量问题",

    "need_review":False,

    "approved":False,

    "status":"",

    "answer":""

})


print(result)