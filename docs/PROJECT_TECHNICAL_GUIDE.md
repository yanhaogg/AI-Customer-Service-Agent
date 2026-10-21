# ServAI 项目技术说明

版本基准：2026 年 10 月 21 日的代码。

ServAI 是一个以日常电子产品商城为业务背景的智能客服实战项目。React 前端提供商品、购物、售后与管理员界面；FastAPI 后端负责身份校验、数据库读写和业务状态转换；LangGraph 组织大模型查询与人工客服辅助流程。业务数据保存在 PostgreSQL，商品图片与售后凭证保存在本地文件系统。

理解这个项目时，需要分清三件事：商城规则由程序执行；Agent 根据受限数据生成回答或建议；管理员通过业务接口确认处理。多 Agent 是同一后端中的多个逻辑角色和子图，不是多个独立部署的服务。

## 文档导航

- 本文：系统架构、技术栈、数据库关系、完整业务与 Agent 流程、启动方式、代码阅读路径。
- [逐文件代码说明](CODE_FILE_REFERENCE.md)：每个项目源码文件的用途、主要对象与所在层，包含兼容文件和旧演示文件。
- [数据库与接口参考](DATABASE_AND_API_REFERENCE.md)：26 个 ORM 表的字段、外键，以及 76 项当前注册的业务 HTTP 操作。
- 更细的模块操作说明位于 [backend/scripts](../backend/scripts)，例如 [Agent 说明](../backend/scripts/README_agent.md)、[售后说明](../backend/scripts/README_aftersales.md)、[手动待办说明](../backend/scripts/README_support_tasks.md)。

建议先阅读本文第 1～4 节，建立整体认识；再按兴趣阅读购物、Agent、人工接待、待办流程；最后用两个参考文档逐个定位文件和接口。

## 1 当前实现范围

| 领域 | 当前能力 | 主要入口 |
| --- | --- | --- |
| 账号与权限 | 普通用户注册登录；超级管理员本地创建；数据库角色校验 | `/login`、`/register`、`/profile` |
| 商品展示 | 数据库商品、分类、搜索、详情、图片、首页选品 | `/home`、`/products` |
| 商品管理 | 新增、编辑、逻辑删除、图片上传、演示售价与库存设置 | `/admin/products`、`/admin/homepage` |
| 购物订单 | 购物车、多选结算、立即购买、地址、演示支付、取消、发货、确认收货 | `/cart`、`/checkout`、`/orders` |
| 售后 | 催发货、退款规则、申请凭证、人工审核、退货与验收 | 订单页面中的售后面板 |
| 客户历史 | 本人聊天记录、浏览历史、未读状态 | `/chat`、`/history` |
| 客户智能客服 | Manager 调度商品、订单、售后 Agent，结合历史回答 | `/chat` |
| 人工接待 | 管理员查看全部客户会话、回复、接管、结束接待、未读筛选 | `/admin/support` |
| 人工客服助手 | 聊天摘要、用户诉求、建议回复，采用后可编辑发送 | 人工接待页面 |
| 订单异常与待办 | 管理员选择订单、手动分析、确认创建、认领与处理记录 | `/admin/tasks` |

当前支付、库存和退款是演示业务，未接真实支付渠道、仓库或承运商轨迹。知识库检索、向量检索、售后图片内容预审、商品运营 Agent 均没有接入。售后图片目前用于存储、展示和人工审核，不代表已经具备自动图像判定能力。

订单异常跟进已经改为手动模式：没有定时扫描器、后台自动分析队列或自动创建待办。页面定时刷新未读数、会话和待办列表只是读取数据，不是后台扫单。

## 2 技术栈与各自职责

### 2.1 前端

| 技术 | 项目声明版本 | 用途 |
| --- | --- | --- |
| React、React DOM | `^19.2.8` | 组件、状态、Effect、页面渲染 |
| React Router DOM | `^7.18.4` | 前端路由、导航、URL 参数 |
| Vite | `^8.3.0` | 开发服务器、接口代理、生产构建 |
| JavaScript ES Modules、JSX | 项目源码形式 | 页面和组件开发；没有 TypeScript 编译流程 |
| CSS | `index.css`、`storefront.css`、`navbar.css` | 全局样式、商城布局、导航适配 |
| Fetch、AbortController | 浏览器原生 API | HTTP 请求与过期请求取消 |
| React Context | React 内置 | 全局登录身份与角色，不使用 Redux |
| ESLint | `^10.10.0` | JavaScript、React Hooks 与热更新规则检查 |

前端依赖范围来自 `frontend/package.json`，精确解析由 `frontend/package-lock.json` 决定。`@types/react` 虽然出现在开发依赖中，实际应用仍是 `.js/.jsx`。

### 2.2 后端与数据库

| 技术 | 后端依赖版本 | 用途 |
| --- | --- | --- |
| Python | 当前虚拟环境为 3.12 | API、数据处理、Agent 与脚本 |
| FastAPI | `0.143.0` | HTTP 路由、依赖注入、OpenAPI |
| Uvicorn | `0.54.0` | ASGI 服务进程与本地热重载 |
| Pydantic | `2.14.1` | 请求字段、工具参数、模型结构化输出校验 |
| SQLAlchemy | `2.1.4` | ORM、SQL 查询、事务与行锁 |
| PostgreSQL | 项目配置的数据库服务 | 持久化、外键、JSONB、唯一约束与并发控制 |
| bcrypt | `4.1.2` | 密码哈希与验证 |
| python-jose | `3.5.0` | JWT 的签发与校验 |
| python-dotenv | `1.2.4` | 读取本地环境配置 |
| Pillow | `12.3.0` | 商品图及凭证图片的解码、格式与尺寸校验 |
| unittest、FastAPI TestClient | 标准库与测试工具 | 模型替身测试、真实 PostgreSQL 集成测试 |

这里的 PostgreSQL 是服务依赖，不是从 `requirements.txt` 安装的 Python 包。素材采集阶段的 SQLite 文件只是历史商品数据源，不是商城运行数据库。

数据库驱动有一个实际差异：当前虚拟环境同时安装了 `psycopg 3.3.6` 和 `psycopg2-binary 2.9.13`，当前默认方言实际使用 psycopg；`requirements.txt` 显式列出的是 psycopg2-binary。新环境可以明确使用 `postgresql+psycopg2://...`，与现有依赖清单对应，避免依赖默认驱动选择。

### 2.3 大模型与 Agent

| 技术 | 版本或配置 | 用途 |
| --- | --- | --- |
| LangGraph | `1.2.15` | Manager 主图、专业 Agent 子图和辅助工作流 |
| langchain-core | `1.6.10` | 消息类型、StructuredTool、模型工具协议 |
| langchain-openai | `1.7.1` | `ChatOpenAI` 兼容客户端，实际请求 DeepSeek |
| DeepSeek | `.env` 中的 `DEEPSEEK`，默认 `deepseek-flash` | 对话、工具选择、总结、结构化建议 |

使用 `langchain-openai` 不表示当前调用的是 OpenAI 模型。它在这里充当兼容接口客户端，模型服务地址由 `DS_API_BASE` 等配置决定。

项目没有训练或微调大模型。已有千帆和 Embedding 配置不参与当前运行链路。数据库检索是受约束的 SQL 查询，不是 RAG 或向量相似度检索。

## 3 目录结构

以下是承担职责的目录，不展开虚拟环境、安装依赖、构建产物和数百条商品素材。

```text
AI-Customer-Service-Agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI 应用入口
│   │   ├── api/                    HTTP 接口
│   │   ├── auth/                   JWT、密码、身份与角色依赖
│   │   ├── schemas/                账号请求结构
│   │   ├── database/               ORM、数据库会话、手工迁移
│   │   ├── services/               售后、未读、待办业务逻辑
│   │   └── agent/                  Manager、专业子图、工具与辅助 Agent
│   ├── scripts/                    导入、建表、管理员创建、检查说明
│   ├── tests/                      自动化测试
│   ├── requirements.txt
│   └── test.py                     早期演示脚本，当前不应作为测试入口
├── frontend/
│   ├── index.html                  浏览器 HTML 入口
│   ├── src/
│   │   ├── main.jsx                React 挂载入口
│   │   ├── router/                 当前路由表
│   │   ├── auth/                   登录上下文
│   │   ├── pages/                  业务页面
│   │   ├── components/             复用组件
│   │   ├── lib/                    当前请求封装、格式化与轮询逻辑
│   │   ├── api/                    早期请求封装，当前页面没有引用
│   │   ├── data/                   早期静态商品数据，当前页面没有引用
│   │   └── *.css                   样式
│   ├── public/、src/assets/         图形静态资源
│   ├── package.json、package-lock.json
│   ├── vite.config.js
│   └── eslint.config.js
├── product_materials/
│   ├── products.jsonl              标准导入数据，一行一个商品
│   ├── products.json               同批商品的 JSON 汇总
│   ├── categories/                 分商品保存的图片、介绍和原始来源
│   ├── sources/                    数据源快照、说明、被剔除候选
│   ├── scripts/                    素材采集、清理与校验
│   ├── gallery.html                离线素材浏览页
│   ├── admin_uploads/              管理员上传的商品图，使用时生成
│   └── private_refund_evidence/    私有售后凭证，使用时生成
└── docs/                           本套系统技术文档
```

`.env`、初始管理员密码文件、本地数据库文件、图片本体不需要作为普通源码阅读。`venv/`、`node_modules/` 和 `dist/` 分别是运行环境、第三方依赖、前端构建结果，也不是需要逐个修改的业务代码。

## 4 一次页面请求如何穿过系统

```mermaid
flowchart LR
    B[浏览器 React 页面] --> F[lib 请求函数]
    F --> V[Vite 代理或指定 API 地址]
    V --> API[FastAPI 路由]
    API --> AUTH[身份与角色依赖]
    AUTH --> S[业务函数或 Agent]
    S --> DB[(PostgreSQL)]
    S --> FILES[本地图片文件]
    S --> LLM[DeepSeek 兼容接口]
    DB --> API
    API --> B
```

### 4.1 前端真正的入口

`frontend/index.html` 引入 `src/main.jsx`。`main.jsx` 把 `AuthProvider` 包在 `Router` 外面，再挂载到 `#root`。

`router/index.jsx` 决定页面。`/chat` 对应 `Chat.jsx`，后者转导出 `SavedChat.jsx`；`/orders` 对应 `Orders.jsx`，后者转导出 `ShopOrders.jsx`。因此修改聊天和订单列表时，应主要看两个实际实现文件。

`App.jsx` 不在当前挂载链路中。它保留了早期向 `/chat` 提交固定订单号的页面，而当前后端没有这个旧接口。不能根据这个文件理解现有客服架构。

### 4.2 请求封装

- `lib/catalog.js` 的 `useCatalog` 请求公开商品接口；`apiUrl` 统一拼接地址。
- `lib/shop.js` 的 `shopRequest` 自动带上 Bearer Token，`useShop` 管理请求状态与重试。
- `VITE_API_BASE_URL` 为空时请求同源路径，由 Vite 把 `/auth`、`/api/catalog`、`/api/shop`、`/api/activity`、`/api/admin` 代理到 `127.0.0.1:8000`。
- `keepPrevious` 允许刷新时保留已有内容，避免编辑框和会话因轮询闪烁或卸载。

当前更新采用普通 HTTP 请求与定时轮询，没有 WebSocket、SSE 或逐字流式输出。

### 4.3 后端分层

`app/main.py` 创建 `server = FastAPI()`，注册各个路由，并允许本地前端的跨域来源。当前没有后台扫描的应用生命周期任务。

`api/` 负责 HTTP 参数和响应；`services/` 放复用业务规则；`database/` 定义表和数据库会话；`agent/` 组织模型与只读工具。这不是完全拆分为 repository 层的架构：一些 SQL 和规则直接位于 API 文件中，例如购物流程的 `quote`、`expire_orders`、库存释放函数就在 `api/shop.py`。

## 5 身份与权限

### 5.1 登录链路

1. 注册接口用 Pydantic 校验账号密码，额外传入 `role` 会被拒绝。
2. 密码使用 bcrypt 哈希保存，不保存明文。
3. 登录成功后签发 HS256 JWT，包含 `user_id` 和 24 小时的过期时间。
4. 浏览器把 Token 放在 `localStorage`。`AuthProvider` 请求 `/auth/me`，取得数据库中的账号角色。
5. 后端每次通过 `get_current_user` 校验 JWT、有效期并读取用户；管理员接口再调用 `require_superadmin`。

当前只有 `user`、`super_admin` 两种角色，没有独立的普通客服角色。文档中的“管理员接待”和“客服认领”，实际由超级管理员账号操作。

### 5.2 前后端各负责什么

前端的 `ShopShell`、页面条件和导航负责展示登录提示、隐藏管理控件。后端依赖才是权限执行点。修改浏览器缓存、直接访问管理 URL 或在请求中伪造角色，都不能绕过数据库角色校验。

商品浏览是公开功能；购物、聊天和历史记录要求登录；管理员可通过专用工作台查看客户会话。普通用户的订单和历史查询始终限制为本人。

同一浏览器同源标签页共享 `localStorage`，因此默认共享登录账号。若需要同时测试两个账号，可以使用不同浏览器或独立隐私窗口；项目没有实现每个标签页独立身份。

### 5.3 超级管理员创建

没有公开管理员注册接口。可信后端主机上运行 `scripts/create_superadmin.py` 创建账号；脚本拒绝覆盖已有账号或把已有普通账号自动提升为管理员。随机生成的初始密码文件只用于本地保存，不应写入技术文档或提交版本库。

## 6 数据库设计与 ID 关联

当前 ORM 注册 26 张表，包含 2 张历史保留表：早期 `orders` 和已停用的 `support_scan_state`。现行业务订单使用 `shop_orders`。

### 6.1 按业务分组

| 分组 | 表 |
| --- | --- |
| 用户 | `users` |
| 商品资料 | `categories`、`products`、`product_sources`、`media_assets`、`product_images`、`product_price_records` |
| 首页 | `homepage_config` |
| 商城交易 | `sale_offers`、`cart_items`、`shipping_addresses`、`shop_orders`、`shop_order_items` |
| 客户活动 | `chat_sessions`、`chat_messages`、`chat_read_states`、`product_browsing_history` |
| 售后 | `refund_requests`、`refund_evidence`、`refund_events`、`shipment_reminders` |
| 手动待办 | `support_tasks`、`support_task_events`、`support_task_previews` |
| 历史保留 | `orders`、`support_scan_state` |

### 6.2 商品怎样在多张表之间对应

`products.id` 是数据库内部唯一商品编号。所有关联商品的业务记录使用这个 ID：图片关联、来源、价格、销售设置、购物车、订单项、浏览记录。

`products.import_key` 保存素材标识，例如 `bb-某SKU`。它是导入追溯键，不应与数据库自增 `id` 混用。`product_sources.source_sku` 保存来源自己的 SKU。

```mermaid
erDiagram
    categories ||--o{ products : category_id
    products ||--o{ product_sources : product_id
    products ||--o{ product_images : product_id
    media_assets ||--o{ product_images : asset_id
    products ||--o{ product_price_records : product_id
    products ||--o| sale_offers : product_id
    users ||--o{ shop_orders : user_id
    shop_orders ||--|{ shop_order_items : order_id
    products ||--o{ shop_order_items : product_id
    users ||--o{ chat_sessions : user_id
    shop_orders ||--o| chat_sessions : order_id
    chat_sessions ||--o{ chat_messages : session_id
    shop_orders ||--o{ support_tasks : order_id
```

### 6.3 图片与媒体资产

图片二进制不放进 PostgreSQL。`media_assets` 保存文件相对路径、SHA-256、尺寸、类型和字节数；`product_images` 保存“哪个商品使用哪个资产”、主图、顺序和来源。

同一个图片内容可以被多个商品共用，所以原始导入批次可以有 400 个商品、400 条图片关联，却只有 395 个唯一资产。这不是商品数据丢失。

商品图片通过 `/api/catalog/media/{asset_id}` 返回，后端验证路径仍在素材根目录中。退款凭证使用另一套登录校验接口，不能作为公开商品图片读取。

### 6.4 资料价格与销售价格

`product_price_records` 保存来源价格与历史参考报价；`sale_offers` 保存当前演示商城的售价、币种、库存和是否可购买。

两者不能混用：有历史参考价不代表可以购买；下单必须存在启用的 `sale_offers` 且库存足够。金额采用 NUMERIC/Decimal，返回 JSON 时常转换为字符串，避免浮点误差。结算不混合币种，也不会自行换算美元和人民币。

### 6.5 订单为什么保存快照

`shop_order_items` 保存下单时名称、单价、数量和图片资产；`shop_orders.shipping_address` 保存下单时地址 JSON。之后修改商品或地址簿，不应改变既有订单内容。

## 7 商品展示与管理流程

商品数据最初来自 `product_materials/products.jsonl`。导入脚本校验 JSON、原始来源、图片存在性与哈希，在一个事务中写入六张商品资料表。来源和图片按唯一键去重，重复导入保留商品身份及人工审阅字段。

原始批次是 400 条历史电子产品素材、12 个分类。它是采集批次规模，不代表管理员增删后数据库永远有 400 个可见商品。

首页优先读取 `homepage_config` 中管理员选择的主推、侧栏与推荐商品。无配置或主推商品不可展示时使用默认规则：音频类优先 Marshall、JBL、Harman Kardon，再补手机、电脑及其他分类的代表商品。这是程序排序，不是 Agent 推荐。

公开目录当前把 `draft`、`reviewed`、`published` 都作为可展示状态，用于本地素材演示。`deleted` 不展示。因此“导入商品默认为 draft”和“前端能展示”并不冲突；是否能结算还要看销售设置。

管理员编辑有两层版本检查：商品通过 `updated_at` 防止覆盖他人的编辑；首页配置通过 `revision` 防止旧版本覆盖。商品删除是逻辑删除，并处理首页选品引用；既有订单快照继续保留。

## 8 购物与订单状态

```mermaid
stateDiagram-v2
    [*] --> pending_payment: 创建订单并预占库存
    pending_payment --> paid: 模拟支付
    pending_payment --> cancelled: 用户取消或访问时处理超时
    paid --> shipped: 管理员录入物流
    shipped --> completed: 用户确认收货
    paid --> refunded: 规则或人工模拟退款
    shipped --> refunded: 售后审核完成
    completed --> refunded: 售后审核完成
```

结算顺序是：前端选择商品与地址 → 预览接口重新计价 → 创建订单时重新校验价格、币种和库存 → 锁定商品销售行 → 写订单与明细 → 减少库存 → 根据选择清理购物车 → 提交事务。后端不信任前端显示的金额。

下单请求带 `request_key` 和请求内容指纹。同一个请求重复提交返回原订单；同一个编号用于不同内容会冲突，避免重复下单。

未支付订单默认 30 分钟过期。当前过期处理是 `expire_orders` 在部分购物接口访问时执行的惰性回收，每次最多处理一批；它不是定时后台任务。取消和过期会释放预占库存；模拟支付不会再扣一次库存。

管理员发货需要订单为 `paid`，并且没有阻止发货的进行中售后；发货时填写快递公司与单号。这里没有请求真实快递服务。

## 9 售后和退款流程

退款金额与是否自动处理由后端规则决定，不由大模型决定，也不接收客户随意填写的退款金额。

| 当前情况 | 路由 |
| --- | --- |
| 已支付未发货，支付后 24 小时内，未收到货，普通“不想要/拍错/改变主意”原因 | 自动整单模拟退款 |
| 发货后、已收货、支付超过 24 小时、质量/破损/支付异常等 | 人工审核 |
| 已收货且人工同意退货 | 提供退货地址，用户填写退货单号，客服验收后退款 |
| 待支付 | 使用取消订单，不走退款 |

申请收集原因、情况说明、确认联系电话、是否收货；质量和破损问题要求图片凭证。凭证有格式、大小、数量及归属校验。

退款状态包括 `review_pending`、`awaiting_return`、`return_in_transit`、`refunded`、`rejected`、`withdrawn`。审核动作、说明和处理者保存在 `refund_events`。唯一约束避免同一订单并行存在多个活动申请，重复退款也不能重复回补库存。

催发货保存在 `shipment_reminders`，同一订单 24 小时内重复催促复用记录。它与客服待办是不同业务记录：催发货由客户主动发起；待办由管理员查看分析后确认创建。

## 10 聊天、会话与未读状态

### 10.1 会话与订单绑定

`chat_sessions` 保存会话归属、商品上下文、订单上下文、标题和人工接待状态。`chat_messages` 保存消息本身。

同一订单的普通咨询、催发货、退款售后、转人工与通用创建会话请求，都复用该订单唯一会话。实现由 `services/aftersales.py::order_session`、订单行锁和 `chat_sessions.order_id` 唯一约束共同保证。未绑定订单的普通咨询可以有多个会话。

### 10.2 一轮客户消息的处理

1. 验证会话属于当前用户，校验 `request_key`，拒绝同一会话同时生成多个回复。
2. 保存客户消息和一条 `pending` 的 assistant 占位消息，先提交事务。
3. 若正在等候或接待人工，保存送达提示，不调用客户 Agent。
4. 否则取得最近完成的聊天与订单线索，调用 `support_agent.invoke`。模型请求期间不持有会话写锁。
5. 返回后重新锁定会话；只有占位消息仍属于这次生成，才写入结果。
6. 回复和 `agent_metadata` 一同保存；失败保留用户输入并支持重试。

超过两分钟仍在途的消息会在读取时恢复为失败状态；晚到的旧回复不能覆盖已重试或已被人工接管的内容。

### 10.3 消息角色与显示方向

- `user`：客户发言。
- `assistant`：模型答复或系统送达提示。
- `human_agent`：人工客服发言，保存 `staff_user_id`。

用户端把本人的 `user` 消息放右侧；管理员端使用服务端计算的 `is_mine`，只把当前管理员的人工回复放右侧。其他客服、客户和 AI 的消息放左侧。

### 10.4 未读计算

`chat_read_states` 以“会话 ID + 阅读用户 ID”为联合主键，保存单调前进的 `last_read_at`。

用户的未读包括 AI 与人工回复；管理员的未读包括客户消息和其他客服回复，AI 消息不重复计入管理员提醒。生成中的消息不计入未读。

读取会话本身不会清除未读。前端确认页面可见且窗口获得焦点后，提交当前实际取得的 `read_through` 水位。后到的 AI 完成消息使用更新后的时间，仍能计入未读。

管理员未读置顶和 `unread_only` 筛选在数据库分页前执行，而不是只把当前页重新排序。

## 11 客户侧多 Agent 架构

### 11.1 各角色

| 角色 | 文件 | 能力 |
| --- | --- | --- |
| Manager | `agent/graph.py` | 理解问题、委派、审阅结果、继续调度、生成最终答复 |
| 商品咨询 Agent | `agent/specialists.py` 注册、子图构建 | 商品分类、搜索、详情、最近浏览、本人聊天搜索 |
| 订单 Agent | 同上 | 本人订单列表、详情、聊天搜索 |
| 售后 Agent | 同上 | 退款政策、本人订单、聊天搜索 |

三个专业 Agent 使用不同系统职责、独立消息上下文和不同工具白名单。它们默认使用同一 DeepSeek 配置，不意味着必须配置三份模型或三把 Key。

图状态只用于本次请求，当前没有配置 LangGraph 的持久化 checkpointer。长期聊天记录由 PostgreSQL 表保存，下次请求再装配为历史消息；“保存聊天”与“保存完整图执行状态”是两件不同的事。

### 11.2 实际图结构

```mermaid
flowchart TD
    START[客户问题与历史] --> M[manager]
    M -->|委派工具调用| D[dispatch 验证任务与额度]
    D --> P[product_agent 子图]
    D --> O[order_agent 子图]
    D --> A[aftersales_agent 子图]
    P --> D
    O --> D
    A --> D
    D -->|本批任务完成| M
    M -->|无需继续查询| END[统一回答]
```

每个专业子图内部为 `model → tools → model` 循环，直到回答、达到上限或失败。Manager 只能使用三个委派工具，不直接获得数据库工具。`dispatch` 校验 `task` 参数，拒绝额外身份字段和未注册 Agent。

同一轮可以委派多个任务，但当前按顺序执行，不是并行线程调度。有依赖时，Manager 可先取得订单编号，再委派售后 Agent；专业 Agent 不能递归调用其他 Agent，只通过 Manager 分享有限的同轮结果。

### 11.3 八个业务工具

| 工具 | 查询内容 | 使用角色 |
| --- | --- | --- |
| `list_product_categories` | 分类代码与商品数 | 商品 |
| `search_products` | 名称、品牌、型号、分类、币种、预算与库存过滤 | 商品 |
| `get_product_details` | 商品介绍、参数、参考价与演示销售设置 | 商品 |
| `get_my_browsing_history` | 当前用户最近浏览 | 商品 |
| `list_my_orders` | 当前用户订单列表 | 订单、售后 |
| `get_my_order_details` | 当前用户订单明细、状态和物流 | 订单、售后 |
| `get_refund_policy` | 程序定义的演示售后规则与所需材料 | 售后 |
| `search_my_chat_history` | 本人历史聊天关键词搜索 | 三个专业角色 |

工具由 `build_tools(verified_user_id, session_factory, current_message_id)` 在服务端构造。模型参数中没有可自由选择的用户 ID，也不接受任意 SQL。每次数据库查询使用独立只读事务和 SQL 超时。

### 11.4 历史、预算与结果

当前会话历史取最近 20 条完成消息，并按约 2 万字符限制裁剪；当前问题避免重复添加。更早历史按需用工具搜索，不一次加载整个账号的聊天记录。

默认整轮共享 16 次模型调用、24 次业务工具请求、6 次委派；Manager 最多 6 轮，每次专业任务最多 4 次模型调用。单次模型调用最多约 20 秒，节点之间检查 90 秒总预算。这些限制位于 `ModelSettings` 与 `RunBudget`，不是每个 Agent 各有一份无限累加的预算。

`agent_metadata` 保存 `mode=manager_multi_agent`、模型名、总调用数、Manager 轮数、专业角色与完成状态、查询工具与状态、是否受限。它不保存内部思考、委派全文或完整工具输出。前端的“本次服务分工”和“本次查询依据”读取这些字段。

这是工具权限的程序约束加模型提示约束：数据库身份和可用工具由程序强制限制；答复准确性仍需要模型遵循事实，不能把提示词理解为对所有回答内容的绝对保证。

## 12 人工接待与人工客服助手

### 12.1 接待状态

`human_status` 包括 `none`、`waiting`、`active`、`closed`。管理员可以查看全部客户会话；只查看不会暂停 AI。发送人工回复会接管并暂停客户 Agent；结束接待后下一条客户提问可继续走 AI。

管理员列表同时支持全部、AI 咨询、待接待、接待中、已结束，以及只看未读。后台按当前管理员分别计算未读，不把一个管理员的阅读状态强加给其他人。

### 12.2 人工客服助手是另一条子流程

`agent/staff_assistant.py` 的图为：读取已验证业务事实 → 模型输出结构化建议。它不经过客户 Manager 的委派循环。

打开会话时前端调用 `/api/admin/support-sessions/{id}/assistant`，返回：

```json
{
  "summary": "聊天摘要",
  "customer_needs": ["用户当前诉求"],
  "suggested_reply": "回复草稿",
  "snapshot_version": "服务端计算的会话版本"
}
```

接口绑定的是会话客户身份，不是管理员自己的订单身份。最多取最近 50 条消息，每条最多 3000 字符，总聊天文本最多 24000 字符；关联订单、商品、退款政策和未完成待办用于辅助核实。

建议只展示在管理员页面，不作为一条聊天消息保存。点击“采用建议”后填入现有回复框，可编辑并手动发送。新消息或相关版本变化会提示建议过期，轮询不会反复调用模型或覆盖草稿。

## 13 手动订单异常跟进与待办

这是与客户 Manager 分开的管理员工作流，不是定时后台任务。

```mermaid
flowchart TD
    A[管理员选择订单] --> B[点击分析所选订单]
    B --> C[程序核实当前订单与规则]
    C -->|存在可跟进事项| D[OrderFollowupAgent 生成分析与草稿]
    C -->|未命中规则| N[显示结果 不建待办]
    D --> E[保存30分钟有效预览 不建待办]
    E --> F[管理员确认创建]
    F --> G[重新核对事实与预览归属]
    G --> H[创建或返回已有待办]
    H --> I[认领 备注 手动完成或忽略]
```

### 13.1 现有规则

- 已支付满 48 小时未发货，且没有进行中售后。
- 发货满 7 天未确认收货，且没有进行中售后。
- 退款申请待审核满 24 小时。

规则只是手动分析时的内部参考。未命中不调用异常分析生成候选任务；长期未确认收货也不等于已证实物流丢件。

### 13.2 为什么要先保存预览

`support_task_previews` 保存管理员、订单、异常来源、事实指纹、模型建议和过期时间。创建接口只接受 `preview_id`，不信任前端自拟的建议、用户身份或订单事实。

确认时检查预览属于当前管理员、未过期，且当前订单事实与分析时一致。订单已变化会要求重新分析；相同订单、类型和来源重复确认返回已有待办。

### 13.3 待办生命周期

状态为 `pending`、`in_progress`、`resolved`、`dismissed`。认领与更新使用先锁订单、再锁任务的固定顺序，防止两个管理员同时抢占。完成和忽略必须有说明；事件保存在 `support_task_events`。

列表和详情读取不会自动建单、分析或关闭任务。订单事实变化时，旧建议不再显示，但待办仍由客服核实后手动完成或忽略。完成待办本身不改变发货、退款等业务状态。

`agent/order_followup.py` 接收程序核实后的快照，输出 `analysis`、`next_steps`、`suggested_reply`，没有业务写工具。对已有待办重新分析时，结果也经过版本复核，旧模型结果不能覆盖更新后的事实。

## 14 事务、并发与一致性

| 场景 | 主要措施 |
| --- | --- |
| 重复注册 | 用户名唯一约束，处理提交冲突 |
| 并发结算、取消、发货 | 商品销售行、用户或订单行锁；后端重新计价 |
| 重复下单 | `request_key`、内容指纹、用户与请求编号唯一约束 |
| 重复客户消息 | 会话、请求编号、角色联合唯一；保留占位消息 |
| 重复人工回复 | 请求编号幂等处理 |
| 同订单开多个会话 | 统一创建函数、订单锁、订单关联唯一约束 |
| 多人修改首页或商品 | `revision` / `updated_at` 乐观版本检查 |
| 多次退款或库存恢复 | 活动退款唯一约束、退款成功约束、`stock_restored` 标记 |
| 同图多商品 | `media_assets.sha256` 唯一，商品图关系独立 |
| 多管理员认领待办 | 固定锁顺序，检查负责人，冲突返回 409 |
| 多次确认待办 | 订单、类型、业务来源联合唯一，重复返回已有任务 |
| 模型请求过慢或结果过时 | 先释放事务，返回后检查请求标识与事实版本 |

SQLAlchemy 的 `create_all(checkfirst=True)` 只创建缺失表，不会把所有旧表自动改成新结构。项目依赖若干显式迁移函数和脚本，没有配置 Alembic 版本迁移链。

## 15 配置与运行

### 15.1 必需配置

配置放在 `backend/.env`；下面全部是占位值，不能直接用于实际登录或调用。

```dotenv
DATABASE_URL=postgresql+psycopg2://DB_USER:DB_PASSWORD@127.0.0.1:5432/customer_service
SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
DS_API_KEY=REPLACE_WITH_YOUR_KEY
DS_API_BASE=https://api.deepseek.com
DEEPSEEK=deepseek-flash
```

- `DATABASE_URL`：环境变量优先，否则读取本地配置，再否则使用代码中的本地开发默认值；建议明确设置，文档不重复默认密码。
- `SECRET_KEY`：JWT 签名密钥，代码从环境读取；缺失会使认证不可用。
- 大模型配置支持现有 `DS_*` / `DEEPSEEK`，以及优先级更高的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；还兼容 `DEEPSEEK_API_KEY`。
- `PRODUCT_MATERIALS_ROOT`：可选，替换默认素材目录。
- `VITE_API_BASE_URL`：可选前端 API 地址；本地同源代理时留空。
- 原 `SUPPORT_TASKS_ENABLED`、`SUPPORT_TASK_SCAN_SECONDS` 已不参与运行。修改它们不会恢复后台扫单。

模型配置由调用时重新读取，但数据库引擎与 JWT 配置等在模块导入时初始化。修改环境后重启后端是最明确的验证方式。

### 15.2 已有环境日常启动

从项目根目录开两个 PowerShell 终端。

后端：

```powershell
Push-Location .\backend
& .\venv\Scripts\python.exe -m uvicorn app.main:server --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
Push-Location .\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

商城地址为 `http://127.0.0.1:5173`，接口文档为 `http://127.0.0.1:8000/docs`，OpenAPI JSON 为 `/openapi.json`。

### 15.3 新环境准备顺序

先安装 PostgreSQL 并创建目标数据库；Python 建表脚本不会替你创建数据库服务或数据库本身。然后从项目根目录执行：

```powershell
python -m venv .\backend\venv
& .\backend\venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt

Push-Location .\frontend
npm ci
Pop-Location
```

配置好 `.env` 后初始化数据库和素材：

```powershell
Push-Location .\backend
& .\venv\Scripts\python.exe -m app.database.init_db
Pop-Location

& .\backend\venv\Scripts\python.exe .\backend\scripts\import_products.py --check-only
& .\backend\venv\Scripts\python.exe .\backend\scripts\import_products.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\init_shop.py --seed-demo-offers
& .\backend\venv\Scripts\python.exe .\backend\scripts\init_activity.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\init_aftersales.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\init_support_tasks.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\unify_order_chats.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\create_superadmin.py --username superadmin
```

其中 `--seed-demo-offers` 是显式把资料价格复制为演示售价，并为缺少销售设置的商品初始化模拟库存，不是识别真实市场库存。已有环境不需要为日常启动重复导入整批素材。

`unify_order_chats.py` 用于旧库合并同一订单的多个会话，保留消息与退款关联，建立唯一索引；不要把它当成删除聊天记录的脚本。待办预览表由 `init_support_tasks.py` 创建，初始 `init_db.py` 的导入范围不能替代所有专项升级脚本。

## 16 测试与排查

### 16.1 自动化测试

```powershell
& .\backend\venv\Scripts\python.exe -m unittest discover -s .\backend\tests

Push-Location .\frontend
npm run lint
npm run build
Pop-Location
```

默认测试用脚本化模型替代真实大模型；大部分集成测试依赖可连接的 PostgreSQL，在随机隔离 schema 中建表，结束后清理。不是纯内存测试，也不会把测试订单写入正式业务 schema。

真实模型测试需要显式设置 `AGENT_LIVE_TEST=1`，会实际调用模型服务；完整素材导入的 PostgreSQL 可选测试使用 `CATALOG_PG_TEST=1`。未开启时相应测试会跳过，不能把“跳过”当作执行成功。

### 16.2 常见现象对应位置

| 现象 | 先看哪里 |
| --- | --- |
| 首页商品不符合预期 | `homepage_config`、`api/catalog.py`、`AdminHomepage.jsx` |
| 图片 404 | `media_assets.storage_key`、素材目录、`PRODUCT_MATERIALS_ROOT` |
| 有参考价却不能购买 | 对应 `sale_offers` 是否存在、启用且有库存 |
| 未登录个人中心提示 | `Profile.jsx`、`ShopShell.jsx`、`AuthProvider.jsx` |
| 普通用户管理请求 403 | `auth/dependencies.py` 与数据库 `users.role`，不是前端隐藏问题 |
| 客服不回答 | `agent/config.py`、会话 `human_status`、消息 `status` |
| AI 回答涉及错误订单 | 检查传入的订单上下文和工具归属校验，不能直接放开用户 ID 参数 |
| 未读数量不清除 | `lib/chat.js` 的窗口可见/焦点判断、`chat_read_states` |
| 待办分析有结果但列表没有 | 当前只是预览，需点击“确认创建待办”；还需检查筛选条件 |
| 旧建议突然不显示 | 当前事实指纹已变化，需要重新核实或人工结束待办 |
| 导入后还是 395 个资产 | 图片按内容去重，不是商品数量统计 |

## 17 建议的代码阅读顺序

第一遍看入口与目录：`main.jsx → router/index.jsx → AuthProvider.jsx → backend/app/main.py`。

第二遍跟一条购物链路：`ProductDetail / PurchaseActions → Checkout → api/shop.py → shop_models.py`。重点看后端重新计价、库存锁和订单快照。

第三遍看客户客服：`SavedChat.jsx → api/activity.py::send_message → agent/graph.py → specialists.py → runtime_nodes.py → catalog_tools.py`。把 LangGraph 状态、模型消息协议和业务查询工具分开理解。

第四遍看管理员辅助：`HumanSupport.jsx → StaffAssistant.jsx → api/human_support.py → agent/staff_assistant.py`。

第五遍看手动异常分析：`ManualOrderAnalysis.jsx → api/support_tasks.py → services/support_tasks.py → agent/order_followup.py → SupportTaskPreview / SupportTask`。

最后看测试。测试中的 `ScriptedModel` 能展示 Manager 如何派发任务、子 Agent 如何回报、错误如何处理，比只读提示词更容易理解运行过程。

## 18 容易混淆的历史内容

| 内容 | 当前判断 |
| --- | --- |
| `frontend/src/App.jsx` 与它使用的 `/chat` | 早期演示，不是当前应用入口，也不是当前 API |
| `frontend/src/data/products.js` | 早期虚构商品目录，当前展示已使用数据库 |
| `models.py::Order` / `orders` 表 | 旧演示模型；正式购物链路是 `ShopOrder` / `shop_orders` |
| `backend/test.py` | 仍导入已不存在的 `graph.app`，保留的旧脚本，不能作为当前测试入口 |
| `agent/tools.py`、`agent/nodes.py` | 兼容转导出，实际实现分别在 `catalog_tools.py`、`runtime_nodes.py` |
| `refund_agent` 名称 | 是 `support_agent` 的兼容别名，不是能执行退款的 Agent |
| `support_scan_state` | 历史扫描统计表；当前没有调用扫描器的功能 |
| `product_materials/README.md` 开头的“未连接数据库” | 是采集阶段的说明；当前网站已通过导入脚本使用数据库 |
| `frontend/README.md` | Vite 模板说明；项目业务入口以本文和实际路由为准 |

以上区别用于准确阅读当前项目，不代表要立刻删除旧文件或增加新模块。
