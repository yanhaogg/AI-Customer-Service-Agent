# 聊天记录与浏览历史

普通用户和管理员在 `/api/activity` 的历史接口只返回自己的记录。超级管理员另可通过 `/api/admin/support-sessions` 查看所有客户的 AI / 人工会话，并主动回复接管；普通用户不能访问这些管理接口。浏览历史仍只允许本人和以本人身份执行的 Agent 查询。

## 页面

- `/chat`：新建咨询、历史会话列表、标题搜索、分页、恢复聊天和删除会话。
- `/chat?session={id}`：刷新或重新登录后恢复指定会话。
- `/history`：最近浏览、浏览次数、单条移除和清空。入口在个人中心“最近浏览”。
- 商品或订单的“咨询客服”会建立带对应商品或本人订单上下文的会话。

客服页面要求登录；消息保存在服务端，不再仅保留于前端内存。当前 Agent 已接入 DeepSeek 自主查询工具循环，自动结合最近 20 条已完成消息；需要更早上下文时可搜索本人历史聊天。工具仅支持查询，没有实际退款执行能力。配置与权限边界见 `README_agent.md`。

## 表结构

| 表 | 主要内容 |
| --- | --- |
| chat_sessions | 用户、会话标题、关联商品/订单、上下文名称快照、创建和更新时间 |
| chat_messages | 会话、用户/助手/人工客服角色、消息正文、请求编号、回复状态、创建和更新时间 |
| product_browsing_history | 用户、商品、名称/图片引用快照、首次/最近浏览时间、次数、最近访问编号 |

消息状态为 `pending`、`completed`、`failed`。助手消息另以 `agent_metadata` 记录模型及本轮工具调用摘要。每轮用户消息和助手消息使用相同 `request_key`，组合 `(session_id, request_key, role)` 唯一。删除会话通过外键级联删除其消息。

用户消息先提交到数据库，再调用 Agent，生成过程中不持有会话写锁。失败时保留用户消息和失败状态，重试复用同一请求编号，不重复插入用户消息。重复的在途请求返回 202，同一会话正在回复时其他新消息返回 409。超过两分钟仍在途的回复在读取会话时标为中断，可重试；迟到的旧回复不会覆盖重试后的结果。

会话按最近更新时间排序，每页 20 个，最多 500 个会话；每个会话最多 2000 条消息。消息初次取最近 50 条，使用 `before_id` 加载更早消息。

浏览记录只在已登录用户成功打开商品详情时自动写入。每个用户每个商品一条记录，同次页面访问重试不会增加次数，再次打开商品则增加次数并置顶。每页 20 条，保留最近 500 个不同商品；匿名浏览不保存、不追溯登录前的记录。删除或不可展示的商品保留历史快照并标记不可查看。

## 初始化

项目根目录执行（本地已执行，可重复运行，不清空现有表）：

```powershell
& backend/venv/Scripts/python.exe backend/scripts/init_activity.py
```

新环境还需先初始化用户、商品和购物相关表。统一 `app.database.init_db` 也已包含这三张新表。

## 接口

全部要求 Bearer JWT，用户身份从令牌及数据库取得，不接受客户端指定 `user_id`：

- `GET/POST /api/activity/sessions`：历史会话/新建会话。
- `GET/DELETE /api/activity/sessions/{id}`：恢复/删除本人会话。
- `POST /api/activity/sessions/{id}/messages`：保存用户消息并调用现有 Agent。
- `POST /api/activity/browsing`：记录详情访问。
- `GET/DELETE /api/activity/browsing`：分页浏览记录/清空本人记录。
- `DELETE /api/activity/browsing/{id}`：移除本人一条记录。

旧的匿名 `POST /chat` 已移除，前端统一使用带认证的会话接口。历史上仅存在前端内存中的聊天无法补录。

验证：`backend/tests/test_activity.py` 使用独立临时 PostgreSQL schema，覆盖消息持久化、上下文归属、重复提交、失败重试、在途请求和迟到回复、消息分页、会话删除级联、浏览去重和跨用户隔离。

## 未读消息

执行 `python scripts/init_chat_unread.py` 创建 `chat_read_states`（`init_activity.py` 也会创建该表）。每个账号、每个会话分别记录 `last_read_at`；删除会话时级联清理。旧消息初始作为未读，查看后清除。

用户 `GET /api/activity/unread` 获取本人未读总数及各会话数量，管理员 `GET /api/admin/support-sessions/unread` 获取所有客户会话的未读数。会话列表也返回 `unread_count`。用户未读包括 AI / 人工回复；管理员未读包括客户消息及其他客服回复，AI 回答不重复提醒管理员。自己发出的消息和生成中的消息不计入未读。

会话详情返回 `read_through`，前端在标签页可见且获得焦点时，通过 `POST /api/activity/sessions/{id}/read` 或管理员的 `POST /api/admin/support-sessions/{id}/read` 提交 `{ "read_through": "详情返回的时间" }`。单纯获取会话不会清除未读；水位只前进，迟到的 AI 回复仍会变为未读。前端每 5 秒刷新提醒，用户会话每 2.5 秒、管理员会话每 4 秒刷新内容。

管理员会话列表默认先按“是否有未读”降序，再按最近更新时间、会话 ID 降序排列；`GET /api/admin/support-sessions?unread_only=true` 仅返回未读会话，可与 `status` 同时使用，排序与筛选均先于分页。查看会话后即使从未读列表中移除，右侧当前打开的会话仍保持显示。
