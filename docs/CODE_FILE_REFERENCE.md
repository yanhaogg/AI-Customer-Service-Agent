# ServAI 逐文件代码说明

对应 [系统技术说明](PROJECT_TECHNICAL_GUIDE.md)。以下覆盖当前仓库的全部 129 个第一方 Python、JavaScript、JSX 与 CSS 源码/配置文件；不展开第三方依赖、虚拟环境、缓存和构建产物。

## 阅读规则

API 文件对应 HTTP 边界，services 对应复用业务规则，database 对应持久化，agent 对应模型与图执行。前端 pages 是页面，components 是复用界面，lib 是请求与状态封装。表中明确标注的旧文件或兼容转导出，不应误认为另一条正在运行的业务链路。

## backend/app

| 文件 | 功能与关键实现 |
| --- | --- |
| [__init__.py](../backend/app/__init__.py) | Python 包标记；本文件没有独立业务实现。 |
| [main.py](../backend/app/main.py) | FastAPI 应用入口，创建 server、注册九类 API 路由与本地 CORS；当前不启动任何订单扫描器。 |

## backend/app/api

| 文件 | 功能与关键实现 |
| --- | --- |
| [activity.py](../backend/app/api/activity.py) | 本人会话、消息生成、重试、浏览历史、未读与已读接口；send_message 负责释放事务后调用 support_agent。 |
| [admin.py](../backend/app/api/admin.py) | 首页选品读取和保存；校验商品 ID、互斥位置与 revision，要求超级管理员。 |
| [admin_products.py](../backend/app/api/admin_products.py) | 管理员商品 CRUD、来源/参考价维护、图片上传与转换；逻辑删除、主图维护、updated_at 并发检查。 |
| [aftersales.py](../backend/app/api/aftersales.py) | 订单联系、催发货、退款政策/申请/凭证、撤销、退货物流、管理员审核与催发货处理接口。 |
| [auth.py](../backend/app/api/auth.py) | 公开注册、登录和 /auth/me；注册固定 user 角色，验证 bcrypt 后签发 JWT。 |
| [catalog.py](../backend/app/api/catalog.py) | 公开分类、商品列表/详情、默认或配置首页、媒体文件响应；拼装参考价与演示销售设置。 |
| [human_support.py](../backend/app/api/human_support.py) | 管理员全部会话列表、未读排序、人工回复/结束、客户转人工及客服助手调用；绑定会话客户而非管理员身份查询。 |
| [shop.py](../backend/app/api/shop.py) | 地址、购物车、计价、创建订单、支付/取消/确认收货、销售设置和管理员发货；含库存锁、幂等与惰性超时回收。 |
| [support_tasks.py](../backend/app/api/support_tasks.py) | 手动预览、确认创建、待办列表/详情、重新分析、认领/备注/完成与进入订单会话；没有 /scan 接口。 |

## backend/app/auth

| 文件 | 功能与关键实现 |
| --- | --- |
| [__init__.py](../backend/app/auth/__init__.py) | Python 包标记；本文件没有独立业务实现。 |
| [dependencies.py](../backend/app/auth/dependencies.py) | get_current_user 验证 JWT 并读数据库用户；require_superadmin 检查当前数据库角色，供 FastAPI Depends 注入。 |
| [jwt.py](../backend/app/auth/jwt.py) | 读取 SECRET_KEY，以 HS256 签发包含 user_id 与 24 小时有效期的 Token；不创建用户。 |
| [password.py](../backend/app/auth/password.py) | bcrypt 密码哈希和兼容旧哈希的校验，哈希 cost 为 12。 |

## backend/app/schemas

| 文件 | 功能与关键实现 |
| --- | --- |
| [user.py](../backend/app/schemas/user.py) | UserCreate/UserLogin 参数、用户名清理、密码字节长度限制，拒绝多余字段。 |

## backend/app/database

| 文件 | 功能与关键实现 |
| --- | --- |
| [__init__.py](../backend/app/database/__init__.py) | Python 包标记；本文件没有独立业务实现。 |
| [activity_migration.py](../backend/app/database/activity_migration.py) | 创建缺失的活动表，并为旧 chat_messages 补 agent_metadata；不是通用数据库迁移工具。 |
| [activity_models.py](../backend/app/database/activity_models.py) | ChatSession、ChatMessage、BrowsingHistory、ChatReadState；消息幂等、订单会话唯一和阅读水位模型。 |
| [admin_migration.py](../backend/app/database/admin_migration.py) | 为旧 users 补 role，创建首页配置表；旧用户默认普通角色，不自动提权。 |
| [aftersales_migration.py](../backend/app/database/aftersales_migration.py) | 增补退款时间、人工会话/消息字段、订单与消息状态约束，创建售后表并调整退款会话外键。 |
| [aftersales_models.py](../backend/app/database/aftersales_models.py) | RefundRequest、RefundEvidence、RefundEvent、ShipmentReminder；活动退款与成功退款唯一索引。 |
| [catalog_models.py](../backend/app/database/catalog_models.py) | 六张商品资料表和外键、主图唯一、媒体哈希唯一、来源与价格记录去重约束。 |
| [database.py](../backend/app/database/database.py) | 加载 backend/.env，创建 SQLAlchemy engine、SessionLocal 和 Base；本文件不主动建表。 |
| [homepage_models.py](../backend/app/database/homepage_models.py) | HomepageConfig 单例模型；主推、侧栏/推荐 ID、revision、编辑者与更新时间。 |
| [init_db.py](../backend/app/database/init_db.py) | 初始建表入口，执行 create_all 与管理员/活动/售后迁移；新增专项表仍需相应脚本。 |
| [models.py](../backend/app/database/models.py) | User 账号模型，以及早期 Order/旧 orders 表；现行交易不用这个 Order 模型。 |
| [order_chat_migration.py](../backend/app/database/order_chat_migration.py) | 事务内合并同订单旧会话，迁移消息/退款引用、处理阅读水位并建立订单会话唯一索引。 |
| [session.py](../backend/app/database/session.py) | get_db 请求级数据库会话依赖，yield 后关闭会话；具体提交和回滚由业务代码决定。 |
| [shop_models.py](../backend/app/database/shop_models.py) | SaleOffer、CartItem、ShippingAddress、ShopOrder、ShopOrderItem；销售设置、订单快照与购物唯一约束。 |
| [support_task_models.py](../backend/app/database/support_task_models.py) | 待办、事件、分析预览，以及历史扫描状态模型；SupportScanState 当前仅作历史保留。 |

## backend/app/services

| 文件 | 功能与关键实现 |
| --- | --- |
| [aftersales.py](../backend/app/services/aftersales.py) | 售后规则与自动路由、退款摘要、订单会话复用、人工接管、审计事件和模拟退款/库存恢复。 |
| [chat_unread.py](../backend/app/services/chat_unread.py) | 按阅读者与角色构建未读 SQL、计数、读取水位和单调已读更新；列表查询不隐式清除未读。 |
| [support_tasks.py](../backend/app/services/support_tasks.py) | 手动核实三类事项、生成预览、确认建单、事实指纹、任务详情/锁和重新分析；读取不自动建单或关闭。 |

## backend/app/agent

| 文件 | 功能与关键实现 |
| --- | --- |
| [__init__.py](../backend/app/agent/__init__.py) | Python 包标记；本文件没有独立业务实现。 |
| [budget.py](../backend/app/agent/budget.py) | RunBudget：单次客户请求共享的模型调用、工具调用、委派次数、截止时间及工具轨迹。 |
| [catalog_tools.py](../backend/app/agent/catalog_tools.py) | 八个业务 StructuredTool 及参数模型；绑定已验证用户，独立只读事务查询商品、订单、浏览与聊天。 |
| [config.py](../backend/app/agent/config.py) | ModelSettings、配置优先级、配置异常与 ChatOpenAI 工厂；DeepSeek 兼容接口关闭思考模式。 |
| [graph.py](../backend/app/agent/graph.py) | SupportAgent 主实现；构建 Manager/dispatch/三个专业节点，传递历史和同轮结果，统一汇总、降级和元数据。 |
| [nodes.py](../backend/app/agent/nodes.py) | 兼容入口，只转导出 runtime_nodes.build_nodes；不另有一套 Agent。 |
| [order_followup.py](../backend/app/agent/order_followup.py) | OrderFollowupAgent：管理员手动分析订单快照，校验 analysis/next_steps/suggested_reply 结构化结果；无写工具。 |
| [runtime_nodes.py](../backend/app/agent/runtime_nodes.py) | 专业子图的 model/tools 节点、路由和文本提取；执行工具白名单、参数校验、预算与安全错误反馈。 |
| [specialists.py](../backend/app/agent/specialists.py) | 商品、订单、售后角色注册与提示；委派参数 Delegation，委派工具 schema 和各专业 StateGraph 构建。 |
| [staff_assistant.py](../backend/app/agent/staff_assistant.py) | StaffAssistant：先核实关联业务，再生成 summary/customer_needs/suggested_reply；计算会话版本，不直接发送消息。 |
| [state.py](../backend/app/agent/state.py) | AgentState 与 ManagerState，定义消息、报告和轨迹的状态结构及累加 reducer；不负责持久化。 |
| [tools.py](../backend/app/agent/tools.py) | 兼容入口，只转导出 catalog_tools.build_tools。 |

## backend/scripts

| 文件 | 功能与关键实现 |
| --- | --- |
| [check_agent.py](../backend/scripts/check_agent.py) | 默认仅检查模型配置；--live 发起公开商品的真实模型查询，输出安全结果。 |
| [create_superadmin.py](../backend/scripts/create_superadmin.py) | 本地可信管理员创建 CLI；交互或指定环境变量读密码，可生成凭据文件，拒绝覆盖或直接提升已有用户。 |
| [import_products.py](../backend/scripts/import_products.py) | 校验 JSONL、路径/图片/原始来源，事务导入六张商品表；--check-only 不连接数据库，幂等保留人工字段。 |
| [init_activity.py](../backend/scripts/init_activity.py) | 单独运行活动表创建及 metadata 升级，便于已有数据库更新。 |
| [init_aftersales.py](../backend/scripts/init_aftersales.py) | 先确保活动结构，再执行售后/人工接待字段与表升级。 |
| [init_chat_unread.py](../backend/scripts/init_chat_unread.py) | 仅补 chat_read_states 表，兼容已有库；不修改消息正文。 |
| [init_shop.py](../backend/scripts/init_shop.py) | 创建购物表；--seed-demo-offers 可显式按参考价创建缺失演示售价与初始模拟库存。 |
| [init_support_tasks.py](../backend/scripts/init_support_tasks.py) | 创建待办、事件、手动分析预览及保留的扫描状态表；不启动任务或定时器。 |
| [unify_order_chats.py](../backend/scripts/unify_order_chats.py) | 调用 migrate_order_chats 执行旧订单重复会话合并，输出合并结果。 |

## backend/tests

| 文件 | 功能与关键实现 |
| --- | --- |
| [test_activity.py](../backend/tests/test_activity.py) | 会话/浏览记录归属、消息幂等、失败恢复和并发测试；复用隔离数据库 fixture。 |
| [test_admin_security.py](../backend/tests/test_admin_security.py) | 管理员创建/权限、公开注册禁止提权、首页与商品写操作及并发保护测试。 |
| [test_aftersales.py](../backend/tests/test_aftersales.py) | 退款路由、库存回补、凭证访问、审核/退货、催发货、人工接管与订单会话复用/迁移测试。 |
| [test_agent.py](../backend/tests/test_agent.py) | ScriptedModel 驱动真实 LangGraph；测试多 Agent 分工、依赖结果、工具隔离、共享预算、降级和上下文。 |
| [test_agent_live.py](../backend/tests/test_agent_live.py) | AGENT_LIVE_TEST=1 才运行的 DeepSeek 真实协作和历史测试；使用合成数据与隔离 schema。 |
| [test_catalog_api.py](../backend/tests/test_catalog_api.py) | 目录查询、分类/搜索/分页、首页拼装与媒体接口集成验证。 |
| [test_chat_unread.py](../backend/tests/test_chat_unread.py) | 用户/管理员阅读隔离、延迟回复、只读查询、未读排序与筛选、权限和删除清理测试。 |
| [test_product_import.py](../backend/tests/test_product_import.py) | 素材校验及异常输入；CATALOG_PG_TEST=1 可运行整批 PostgreSQL 导入/幂等/回滚测试。 |
| [test_shop.py](../backend/tests/test_shop.py) | 购物/库存/地址/幂等/订单状态与并发测试；提供随机 schema、合成用户和商品基础 fixture。 |
| [test_staff_assistant.py](../backend/tests/test_staff_assistant.py) | 客服助手权限、客户身份绑定、结构化草稿、无发送副作用、上下文限制、过期版本与错误脱敏。 |
| [test_support_tasks.py](../backend/tests/test_support_tasks.py) | 手动预览不建单、确认建单、重复确认、归属/过期、只读不自动处理、认领竞争与过期分析丢弃。 |

## backend

| 文件 | 功能与关键实现 |
| --- | --- |
| [test.py](../backend/test.py) | 旧退款演示脚本，导入 graph.app；该对象当前不存在，不是现行测试运行入口。 |

## frontend

| 文件 | 功能与关键实现 |
| --- | --- |
| [eslint.config.js](../frontend/eslint.config.js) | 项目 JS/JSX 的 ESLint、Hooks 和 Vite React Refresh 规则，忽略 dist。 |
| [vite.config.js](../frontend/vite.config.js) | React 插件、开发和 preview 的五类路径代理配置；后端目标为本地 8000。 |

## frontend/src

| 文件 | 功能与关键实现 |
| --- | --- |
| [App.css](../frontend/src/App.css) | Vite/早期 App 样式，当前入口未导入。 |
| [App.jsx](../frontend/src/App.jsx) | 早期示例页面，含旧 /chat 请求与固定订单号；当前 main.jsx 不挂载它。 |
| [index.css](../frontend/src/index.css) | 全局基础、早期商城通用样式和聊天气泡基础规则；仍由 main.jsx 引入。 |
| [main.jsx](../frontend/src/main.jsx) | 真实 React 入口：AuthProvider 包裹 Router，导入三份当前样式并挂载 #root。 |
| [navbar.css](../frontend/src/navbar.css) | 导航的 grid/flex 布局与窄屏适配，避免导航出现横向滚动条。 |
| [storefront.css](../frontend/src/storefront.css) | 现行商品、购物、后台、聊天/助手、售后和手动待办布局及响应式样式。 |

## frontend/src/router

| 文件 | 功能与关键实现 |
| --- | --- |
| [index.jsx](../frontend/src/router/index.jsx) | BrowserRouter 业务路由表，映射客户和管理员页面；默认及未知地址回到 /home。 |

## frontend/src/auth

| 文件 | 功能与关键实现 |
| --- | --- |
| [AuthProvider.jsx](../frontend/src/auth/AuthProvider.jsx) | Token 存储、/auth/me 验证、角色和登录状态；处理跨标签页同步及窗口回焦后台验证。 |
| [context.js](../frontend/src/auth/context.js) | 创建 AuthContext，全局身份上下文对象。 |
| [useAuth.js](../frontend/src/auth/useAuth.js) | 封装 useContext(AuthContext)，供页面、组件及请求 Hook 使用。 |

## frontend/src/lib

| 文件 | 功能与关键实现 |
| --- | --- |
| [catalog.js](../frontend/src/lib/catalog.js) | 公开目录请求 Hook、apiUrl、显示名称/价格格式化和商品咨询链接；读取 VITE_API_BASE_URL。 |
| [chat.js](../frontend/src/lib/chat.js) | 用户/管理员未读轮询，以及可见且聚焦时提交已读水位；不生成 AI 消息。 |
| [refunds.js](../frontend/src/lib/refunds.js) | 退款状态到中文展示名称的映射。 |
| [shop.js](../frontend/src/lib/shop.js) | shopRequest、useShop、货币/订单状态格式化；带 Token、请求取消、刷新和保留上次数据。 |
| [supportTasks.js](../frontend/src/lib/supportTasks.js) | 待办状态/类型映射、页面刷新事件和管理员统计轮询；只是读统计，不扫描订单。 |

## frontend/src/api

| 文件 | 功能与关键实现 |
| --- | --- |
| [request.js](../frontend/src/api/request.js) | 旧请求封装，固定 localhost:8000 并读取 localStorage Token；当前页面未引用。 |

## frontend/src/data

| 文件 | 功能与关键实现 |
| --- | --- |
| [products.js](../frontend/src/data/products.js) | 早期虚构商品列表、分类和咨询链接函数；当前目录已改为数据库接口，不使用此数据。 |

## frontend/src/pages

| 文件 | 功能与关键实现 |
| --- | --- |
| [Addresses.jsx](../frontend/src/pages/Addresses.jsx) | 本人收货地址列表、新增/编辑表单和删除操作，使用 ShopShell 登录门控。 |
| [AdminHomepage.jsx](../frontend/src/pages/AdminHomepage.jsx) | 管理员搜索选品、主推/侧栏/推荐配置、顺序调整、revision 保存和冲突提示。 |
| [AdminProducts.jsx](../frontend/src/pages/AdminProducts.jsx) | 商品搜索、分页、创建/编辑/删除、图片上传、参数编辑，并嵌入销售设置编辑器。 |
| [BrowsingHistory.jsx](../frontend/src/pages/BrowsingHistory.jsx) | 本人最近浏览分页、商品跳转、单条删除和清空。 |
| [Cart.jsx](../frontend/src/pages/Cart.jsx) | 购物车数量调整、移除、多选商品及选中项结算入口。 |
| [Chat.jsx](../frontend/src/pages/Chat.jsx) | 兼容页面名，只转导出 SavedChat，不另有聊天实现。 |
| [Checkout.jsx](../frontend/src/pages/Checkout.jsx) | 直接购买或购物车结算、计价预览、地址选择/新增、备注、幂等提交订单。 |
| [Home.jsx](../frontend/src/pages/Home.jsx) | 调用 /api/catalog/home，展示主推/侧栏/推荐及分类，不在前端自行选品。 |
| [HumanSupport.jsx](../frontend/src/pages/HumanSupport.jsx) | 管理员会话列表、未读筛选、消息轮询、人工回复与结束接待；嵌入助手、分工说明及关联待办链接。 |
| [Login.jsx](../frontend/src/pages/Login.jsx) | AuthPage 的登录模式包装。 |
| [OrderDetail.jsx](../frontend/src/pages/OrderDetail.jsx) | 读取本人订单详情并使用 OrderView 展示操作。 |
| [Orders.jsx](../frontend/src/pages/Orders.jsx) | 兼容页面名，只转导出 ShopOrders。 |
| [ProductDetail.jsx](../frontend/src/pages/ProductDetail.jsx) | 数据库商品详情、参数/说明、同类商品、咨询与购买按钮，记录登录用户浏览。 |
| [Products.jsx](../frontend/src/pages/Products.jsx) | 分类/关键词/排序/分页 URL 状态，读取目录并渲染 ProductCard。 |
| [Profile.jsx](../frontend/src/pages/Profile.jsx) | 个人中心、账号身份和业务链接；ShopShell 控制游客登录提示，登录后才显示退出。 |
| [Register.jsx](../frontend/src/pages/Register.jsx) | AuthPage 的普通用户注册模式包装。 |
| [SavedChat.jsx](../frontend/src/pages/SavedChat.jsx) | 实际客户聊天工作区：历史会话、搜索/删除、绑定商品/订单、发送/重试、转人工、未读及分工/工具说明。 |
| [ShopOrders.jsx](../frontend/src/pages/ShopOrders.jsx) | 用户/管理员共享订单列表，按 admin 参数切换接口、筛选和 OrderView 管理操作。 |
| [SupportTasks.jsx](../frontend/src/pages/SupportTasks.jsx) | 手动异常分析入口与待办列表/详情，支持筛选、认领、备注、重新分析、关闭和进入订单会话。 |

## frontend/src/components

| 文件 | 功能与关键实现 |
| --- | --- |
| [AddressForm.jsx](../frontend/src/components/AddressForm.jsx) | 收货人、电话、地区、详细地址、邮编和默认地址的受控编辑表单。 |
| [AftersalesPanel.jsx](../frontend/src/components/AftersalesPanel.jsx) | 退款政策/申请/历史面板，凭证上传、撤回、退货单号及管理员审核/验收交互。 |
| [AgentCollaboration.jsx](../frontend/src/components/AgentCollaboration.jsx) | 根据 agent_metadata.agents 显示本次专业 Agent 分工和执行状态，不展示内部推理。 |
| [AuthPage.jsx](../frontend/src/components/AuthPage.jsx) | 登录/注册共用表单、校验、请求、登录回跳和安全的站内 redirect 处理。 |
| [CatalogImage.jsx](../frontend/src/components/CatalogImage.jsx) | 商品图片地址拼接、加载失败占位和图片展示。 |
| [CatalogStatus.jsx](../frontend/src/components/CatalogStatus.jsx) | 加载、错误与重试等通用界面状态。 |
| [ChatText.jsx](../frontend/src/components/ChatText.jsx) | 有限的聊天文本格式化和安全站内链接，不作为任意 HTML 渲染器。 |
| [ManualOrderAnalysis.jsx](../frontend/src/components/ManualOrderAnalysis.jsx) | 手动筛选/选择订单、请求分析预览、展示结果，再用服务端 preview_id 显式确认建待办。 |
| [Navbar.jsx](../frontend/src/components/Navbar.jsx) | 客户导航、管理员导航、消息未读徽标和未完成待办数量；根据身份显示入口。 |
| [OrderView.jsx](../frontend/src/components/OrderView.jsx) | 共享订单内容与操作组件，连接支付/取消/收货、联系/催发货、管理员发货及售后/待办入口。 |
| [ProductCard.jsx](../frontend/src/components/ProductCard.jsx) | 商品卡片、图片、名称、参考价/演示售价和购买入口。 |
| [ProductVisual.jsx](../frontend/src/components/ProductVisual.jsx) | 早期 CSS 商品示意图；当前业务组件没有引用它。 |
| [ProtectedRoute.jsx](../frontend/src/components/ProtectedRoute.jsx) | 早期只检查本地 Token 的路由包装；当前路由未使用，现行界面使用 ShopShell，后端另行校验。 |
| [PurchaseActions.jsx](../frontend/src/components/PurchaseActions.jsx) | 商品的立即购买、加入购物车及数量/登录/可售状态处理。 |
| [SaleOfferEditor.jsx](../frontend/src/components/SaleOfferEditor.jsx) | 管理员编辑 sale_offers 的演示售价、币种、库存和启用开关，与参考报价编辑分离。 |
| [SecureEvidence.jsx](../frontend/src/components/SecureEvidence.jsx) | 携带 Token 获取私有退款凭证为 Blob URL 展示，并清理 URL；不暴露公开凭证路径。 |
| [ShopShell.jsx](../frontend/src/components/ShopShell.jsx) | 客户/管理员业务页面公共外壳，处理导航、登录中、游客提示和管理员访问提示。 |
| [StaffAssistant.jsx](../frontend/src/components/StaffAssistant.jsx) | 管理员会话打开时生成摘要/诉求/建议，合并并发请求、提示过期，明确采用后才填回复框。 |
| [TrackProductView.jsx](../frontend/src/components/TrackProductView.jsx) | 已登录用户打开详情时提交浏览记录，使用访问键减少重复记次。 |
| [UnreadBadge.jsx](../frontend/src/components/UnreadBadge.jsx) | 未读消息红色数字与无障碍说明。 |

## product_materials/scripts

| 文件 | 功能与关键实现 |
| --- | --- |
| [collect.py](../product_materials/scripts/collect.py) | 按配额采集 400 条历史商品，分类、提取带原文证据的字段、下载/验证图像并保存标准记录。 |
| [download_source.py](../product_materials/scripts/download_source.py) | 按 HTTP Range 并发下载并拼接官方 SQLite 数据源；使用固定源文件大小，须从项目根运行。 |
| [finalize_text.py](../product_materials/scripts/finalize_text.py) | 整理中文摘要和字段语义，更新商品汇总与各商品介绍；顶层执行的离线处理脚本。 |
| [verify_and_preview.py](../product_materials/scripts/verify_and_preview.py) | 逐条校验 JSON Schema、图片哈希和解码，生成 gallery.html、校验报告和拼图；离线脚本。 |

## 配置 文档与非代码资源

| 路径 | 用途 |
| --- | --- |
| [.gitignore](../.gitignore) | 忽略后端 .env 与本地管理员初始密码文件；当前文件不等于一份完整的构建缓存忽略清单。 |
| [package-lock.json](../package-lock.json) | 项目根目录保留的空依赖锁，不是前端安装入口；前端应在 frontend 目录运行 npm。 |
| [frontend/package.json](../frontend/package.json) | 前端直接依赖、版本范围和 dev/build/lint/preview 脚本。 |
| [frontend/package-lock.json](../frontend/package-lock.json) | 前端精确依赖解析结果，npm ci 依赖它。 |
| [frontend/index.html](../frontend/index.html) | 浏览器入口，提供 #root、中文元数据并引入 src/main.jsx。 |
| [frontend/README.md](../frontend/README.md) | Vite 模板说明，不能替代当前业务技术文档。 |
| [frontend/public/favicon.svg](../frontend/public/favicon.svg) | 可公开提供的图标资源；当前 index.html 未显式引用它。 |
| [frontend/public/icons.svg](../frontend/public/icons.svg) | 模板 SVG 图标资源。 |
| [frontend/src/assets/react.svg](../frontend/src/assets/react.svg) | React 模板图标，当前主要页面未引用。 |
| [frontend/src/assets/vite.svg](../frontend/src/assets/vite.svg) | Vite 模板图标，当前主要页面未引用。 |
| [backend/requirements.txt](../backend/requirements.txt) | 后端依赖版本清单，包含 Web、数据库、模型客户端及测试所需组件。 |
| [product_materials/scripts/requirements.txt](../product_materials/scripts/requirements.txt) | 离线素材脚本依赖，如 Pillow 与 jsonschema。 |
| [product_materials/product.schema.json](../product_materials/product.schema.json) | 商品素材的 JSON Schema，供离线校验。 |
| [product_materials/products.jsonl](../product_materials/products.jsonl) | 标准导入来源，一行一条记录；不是网站运行时每次读取的数据库替代品。 |
| [product_materials/products.json](../product_materials/products.json) | 同批标准商品 JSON 汇总。 |
| [product_materials/gallery.html](../product_materials/gallery.html) | 离线生成的素材库浏览页，和 React 商城是两个入口。 |
| [product_materials/collection_report.json](../product_materials/collection_report.json) | 素材采集数量、来源、失败候选和类别汇总。 |
| [product_materials/validation_report.json](../product_materials/validation_report.json) | 素材校验结果。 |
| [product_materials/preview_contact_sheet.jpg](../product_materials/preview_contact_sheet.jpg) | 抽样图片拼图，不参与业务逻辑。 |
| [product_materials/README.md](../product_materials/README.md) | 采集阶段结构与许可说明，开头尚未导入的描述属于当时状态。 |

## 专项说明文档

- [README_activity.md](../backend/scripts/README_activity.md)
- [README_admin.md](../backend/scripts/README_admin.md)
- [README_aftersales.md](../backend/scripts/README_aftersales.md)
- [README_agent.md](../backend/scripts/README_agent.md)
- [README_catalog_api.md](../backend/scripts/README_catalog_api.md)
- [README_import_products.md](../backend/scripts/README_import_products.md)
- [README_shop.md](../backend/scripts/README_shop.md)
- [README_support_tasks.md](../backend/scripts/README_support_tasks.md)

## 素材目录中的重复记录结构

每个 categories/<分类>/<商品目录>/ 下的 product.json、source_original.json、image_metadata.json、introduction.txt / introduction.md、main.jpg 分别是标准资料、原始来源、图片元数据、介绍和图片本体。它们按同一结构重复保存，不是数百个不同功能的代码文件。

sources 保存离线数据源及许可；admin_uploads 与 private_refund_evidence 是运行时文件目录。后端通过数据库路径定位文件，备份不能只导出 PostgreSQL 而遗漏这些目录。
