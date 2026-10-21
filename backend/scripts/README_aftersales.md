# 订单客服、催发货与模拟退款

本项目仍是演示商城：退款表示更新演示订单与退款记录，不调用真实支付网关、不发生资金转账。AI 只读查询规则和状态，不能自行执行退款；确定性后端规则和人工审核接口负责执行。

## 订单入口与会话绑定

- “联系客服”：立即调用本人订单的 contact 接口，创建或复用该订单的咨询会话，再跳转会话页。创建时就写入 `chat_sessions.order_id`，不是仅通过 URL 文本暗示订单。
- “催发货”：仅已支付未发货、无活动售后的订单可催促。保存 `shipment_reminders`，同一订单24小时内不重复创建；同时复用该订单唯一的咨询会话。管理员可在订单页保存跟进说明，发货时自动标记已处理。
- “申请退款/查看售后”：展示规则、材料要求、申请和处理历史。
- 会话页“转人工客服”：用户转人工后，该会话进入管理员工作台的待接待列表；所有 AI 会话也可在全部会话或 AI 咨询中查看。人工接待期间用户新消息不会调用模型，工作台回复以 `human_agent` 保存；结束接待后下一次用户提问恢复 AI。

管理员工作台为 `/admin/support`。管理员必须是 `super_admin`，可查看所有客户 AI / 人工会话并主动回复接管；普通用户仍只能访问本人会话。仅查看会话不会暂停 AI；人工回复后暂停 AI，结束接待后恢复。

## 同一订单共用会话

普通订单咨询、催发货、退款售后、转人工，以及 `/api/activity/sessions` 携带 `order_number` 的创建请求，都复用同一条订单会话。业务类型保存在催发货和退款记录中，不再据此另开聊天。创建时锁定订单行，数据库 `uq_chat_order` 唯一约束防止并发重复；不绑定订单的普通咨询可以有多个会话。

已有数据库执行 `python scripts/unify_order_chats.py`：事务内保留最早的会话 ID，合并消息、退款关联、人工接待状态，再建立唯一索引。聊天内容及消息 ID 保留；重复会话 ID 停用，需从订单或历史列表重新进入。为保证原来的未读消息不被漏掉，合并后部分旧消息可能重新显示为未读。正在生成回复的重复会话会使迁移中止，等待回复完成后可重试。脚本可重复执行。

## 当前业务规则（demo-v1）

| 情况 | 处理 |
| --- | --- |
| 待支付 | 取消订单，释放预占库存，不称为退款 |
| 已支付未发货，支付24小时内，未收货，原因是不想要、拍错、改变主意 | 整单全额自动模拟退款，订单改为 `refunded`，库存只释放一次 |
| 支付超过24小时未发货，或质量、破损、支付异常、其他原因 | 人工审核，审核通过后处理 |
| 已发货但未收到货 | 人工核实物流/拦截/丢失情况，审核可批准退款，不自动恢复可售库存 |
| 已发货或完成且已收到货 | 人工批准退货 → 提供退货地址 → 用户填写退货物流 → 客服确认收到并验收 → 模拟退款 |
| 已收货超过7天 | 继续允许提交人工评估，不自动拒绝；模型不能据此承诺必退 |

本阶段只支持整单全额申请，金额和币种取订单快照，不接受客户端指定退款金额。当前规则不按人民币金额阈值处理外币订单，也不自动换汇。

## 用户需要提供

1. 退款原因和至少10字的情况说明。
2. 确认联系电话、是否已收到货（未发货和已完成状态由后端校验一致性）。
3. 质量/破损问题：至少1张、最多3张照片；其他原因可选。每张不超过5MB，JPEG/PNG/WebP。
4. 需要退货的申请获批后：按客服提供的地址寄回，填写快递公司和单号。建议7天内寄出，超期联系人工评估，系统不自动吞掉申请。

不要收集银行卡、登录密码或验证码。收货地址从订单快照读取，联系电话由用户确认。凭证去除图像元数据并以 JPEG 保存在 `product_materials/private_refund_evidence/`，不登记为公开商品图片。文件只经身份校验的接口读取，申请人和已提交申请的审核人员可以查看，匿名和其他用户不能读取。

## 退款状态

```text
自动符合规则：提交 → refunded
需要审核：review_pending → rejected / withdrawn
未收货人工批准：review_pending → refunded
已收货人工批准：review_pending → awaiting_return → return_in_transit → refunded
寄回前可撤销：review_pending / awaiting_return → withdrawn
```

活动售后期间阻止管理员发货和用户确认收货。驳回或撤销后恢复正常操作。退货在途不能自行撤销，需要人工跟进。未发货成功退款会释放库存；已发货、丢失、退回商品不会自动当作可售新品，需仓库检查后通过销售库存设置另行维护。

每个订单同时最多一笔活动退款、最多一笔成功退款。申请 `request_key` 幂等，订单、申请和库存写入使用事务与行锁；重复审批不重复退款或加库存。退款、发货抢占同一订单锁，发货先成功则申请转人工，退款先成功则不能再发货。

## 数据库与迁移

新增 `refund_requests`、`refund_evidence`、`refund_events`、`shipment_reminders`。扩展订单 `refunded_at` 和状态约束，会话增加接待状态，消息支持 `human_agent` 并记录客服账号。删除聊天不会删除退款工单及审计，工单的会话关联改为空。

项目根目录执行（本地已执行，重复运行不清空数据）：

```powershell
& backend/venv/Scripts/python.exe backend/scripts/init_aftersales.py
```

主要用户接口位于 `/api/shop`：

- `POST /orders/{id}/contact`、`POST /orders/{id}/remind-shipping`。
- `GET /orders/{id}/refund-options`。
- `GET/POST /orders/{id}/refunds`。
- `POST /orders/{id}/refund-evidence`、`GET /refund-evidence/{id}`。
- `POST /refunds/{id}/withdraw`、`POST /refunds/{id}/return-shipping`。
- 转人工为 `POST /api/activity/sessions/{id}/handoff`。

管理员接口位于 `/api/admin`：

- `GET /orders/{id}/refunds`。
- `POST /refunds/{id}/review`，动作是 approve、reject、confirm_return，必须填写处理说明。
- `POST /reminders/{id}/handle`。
- `GET /support-sessions`、`GET /support-sessions/{id}`、`POST /support-sessions/{id}/messages`、`POST /support-sessions/{id}/close`。

测试 `tests/test_aftersales.py` 使用隔离 schema，覆盖订单绑定、归属与客服权限、自动退款幂等、人工审核、私有凭证、退货验收、库存一致性、并发发货退款、催促限频，以及转人工时抑制迟到 AI 回复。
