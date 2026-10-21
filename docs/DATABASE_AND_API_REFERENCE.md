# ServAI 数据库与接口参考

对应 [系统技术说明](PROJECT_TECHNICAL_GUIDE.md)。字段来自当前 SQLAlchemy 模型，接口来自当前 FastAPI OpenAPI 注册结果；它们是代码结构，不是对某个运行数据库行数或已迁移程度的声明。

## 1 表与字段

当前模型注册 26 张表。orders 与 support_scan_state 为历史保留表，其余承担现行业务。PK 表示主键，联合主键需一起理解。类型按 PostgreSQL 方言展开；默认值与业务允许的空值处理仍以模型和请求校验为准。

### cart_items

用户购物车，用户与商品联合唯一。

模型：`CartItem`；定义：[源码](../backend/app/database/shop_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `quantity` | `INTEGER` | 不可空 | — | 商品数量。 |

- 唯一键：`(user_id, product_id)`。

检查约束：

```sql
quantity BETWEEN 1 AND 99
```

### categories

商品分类和可选父分类。

模型：`CatalogCategory`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `code` | `VARCHAR(100)` | 不可空 | — | 分类稳定代码。 |
| `name` | `TEXT` | 不可空 | — | 显示名称。 |
| `parent_id` | `BIGINT` | 可空 | `categories.id` | 可选父分类。 |

- 唯一键：`(code)`。

### chat_messages

客户、AI 和人工客服消息，以及回复状态和协作摘要元数据。

模型：`ChatMessage`；定义：[源码](../backend/app/database/activity_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `session_id` | `BIGINT` | 不可空 | `chat_sessions.id` | 关联会话。 |
| `request_key` | `VARCHAR(64)` | 不可空 | — | 客户端幂等请求编号。 |
| `role` | `VARCHAR(20)` | 不可空 | — | 消息角色：user、assistant、human_agent。 |
| `content` | `TEXT` | 不可空 | — | 消息内容。 |
| `agent_metadata` | `JSONB` | 不可空 | — | 模型、专业角色/工具名称与状态等结构化摘要；不存内部思考。 |
| `staff_user_id` | `INTEGER` | 可空 | `users.id` | 人工回复发送者或会话最近接待者。 |
| `status` | `VARCHAR(20)` | 不可空 | — | 消息生成状态：pending、completed、failed。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |

- 唯一键：`(session_id, request_key, role)`。

检查约束：

```sql
status IN ('pending','completed','failed')
role IN ('user','assistant','human_agent')
```

### chat_read_states

每位阅读者、每个会话的已读水位。

模型：`ChatReadState`；定义：[源码](../backend/app/database/activity_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `session_id` | `BIGINT` | PK；不可空 | `chat_sessions.id` | 关联会话。 |
| `user_id` | `INTEGER` | PK；不可空 | `users.id` | 阅读者 ID，不一定是会话所属客户；管理员分别保存水位。 |
| `last_read_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 已读水位，更新时只前进。 |

### chat_sessions

用户会话、商品/订单绑定与人工接待状态。

模型：`ChatSession`；定义：[源码](../backend/app/database/activity_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `title` | `VARCHAR(100)` | 不可空 | — | 会话或待办标题。 |
| `product_id` | `BIGINT` | 可空 | `products.id` | 商品内部 ID。 |
| `order_id` | `BIGINT` | 可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `context_name` | `TEXT` | 可空 | — | 可展示的商品或订单上下文标识。 |
| `intent` | `VARCHAR(30)` | 不可空 | — | 会话原始意图字段；订单现已统一为 general 复用。 |
| `human_status` | `VARCHAR(20)` | 不可空 | — | none、waiting、active、closed。 |
| `staff_user_id` | `INTEGER` | 可空 | `users.id` | 人工回复发送者或会话最近接待者。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |

- 唯一键：`(order_id)`。

### homepage_config

管理员首页选品单例配置。

模型：`HomepageConfig`；定义：[源码](../backend/app/database/homepage_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `hero_product_id` | `BIGINT` | 不可空 | `products.id` | 首页主推商品。 |
| `spotlight_ids` | `JSONB` | 不可空 | — | 首页侧栏商品 ID 数组。 |
| `featured_ids` | `JSONB` | 不可空 | — | 首页推荐商品 ID 数组。 |
| `revision` | `INTEGER` | 不可空 | — | 首页乐观锁版本。 |
| `updated_by` | `INTEGER` | 不可空 | `users.id` | 最后编辑的管理员。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |

检查约束：

```sql
id = 1
```

### media_assets

按文件哈希去重的媒体元数据，不保存图片二进制。

模型：`MediaAsset`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `storage_key` | `TEXT` | 不可空 | — | 相对素材根目录的文件位置。 |
| `sha256` | `VARCHAR(64)` | 不可空 | — | 文件内容指纹，参与去重。 |
| `width` | `INTEGER` | 不可空 | — | 图片宽度，像素。 |
| `height` | `INTEGER` | 不可空 | — | 图片高度，像素。 |
| `byte_size` | `BIGINT` | 不可空 | — | 文件字节数。 |
| `content_type` | `TEXT` | 不可空 | — | 文件 MIME 类型。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |

- 唯一键：`(sha256)`。

检查约束：

```sql
width > 0 AND height > 0 AND byte_size > 0
```

### orders

早期演示订单，现行购物链路不读写它。

模型：`Order`；定义：[源码](../backend/app/database/models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 可空 | — | 所属用户 ID。 |
| `product_name` | `VARCHAR` | 可空 | — | 早期订单商品名称。 |
| `amount` | `FLOAT` | 可空 | — | 金额；旧 orders.amount 为浮点型，现行金额字段使用 NUMERIC。 |
| `status` | `VARCHAR` | 可空 | — | 当前业务状态，见本表约束或主文状态说明。 |

### product_browsing_history

按用户/商品聚合的浏览记录。

模型：`BrowsingHistory`；定义：[源码](../backend/app/database/activity_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `product_name` | `TEXT` | 不可空 | — | 早期订单商品名称。 |
| `image_asset_id` | `BIGINT` | 可空 | `media_assets.id` | 关联媒体资产。 |
| `first_viewed_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 首次打开商品详情时间。 |
| `last_viewed_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最近浏览时间。 |
| `view_count` | `INTEGER` | 不可空 | — | 累计浏览次数。 |
| `last_visit_key` | `VARCHAR(64)` | 不可空 | — | 最近访问幂等标识。 |

- 唯一键：`(user_id, product_id)`。

检查约束：

```sql
view_count > 0
```

### product_images

商品、来源与媒体资产的关联，包含主图和排序。

模型：`ProductImage`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `source_id` | `BIGINT` | 不可空 | `product_sources.id` | 对应商品来源记录。 |
| `asset_id` | `BIGINT` | 不可空 | `media_assets.id` | 对应媒体资产。 |
| `sort_order` | `INTEGER` | 不可空 | — | 图片顺序，非负。 |
| `is_primary` | `BOOLEAN` | 不可空 | — | 是否主图。 |
| `alt` | `TEXT` | 可空 | — | 替代文本。 |
| `source_url` | `TEXT` | 可空 | — | 原始图片地址。 |
| `resolved_url` | `TEXT` | 可空 | — | 下载最终解析地址。 |
| `rights_status` | `TEXT` | 不可空 | — | 图片授权/使用状态记录。 |
| `downloaded_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 下载时间。 |
| `original_metadata` | `JSONB` | 不可空 | — | 原始图片元数据 JSONB。 |

- 唯一键：`(product_id, source_id, asset_id)`。
- 唯一索引 `uq_product_primary_image`：`(product_id)`，条件 `product_images.is_primary IS true`。

检查约束：

```sql
sort_order >= 0
```

### product_price_records

历史参考报价，与可结算销售设置分离。

模型：`ProductPriceRecord`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `source_id` | `BIGINT` | 不可空 | `product_sources.id` | 对应商品来源记录。 |
| `record_key` | `VARCHAR(64)` | 不可空 | — | 参考价内容指纹，防止重复导入。 |
| `amount` | `NUMERIC(12, 2)` | 不可空 | — | 金额；旧 orders.amount 为浮点型，现行金额字段使用 NUMERIC。 |
| `currency` | `VARCHAR(3)` | 不可空 | — | 金额币种；不自动换汇。 |
| `price_kind` | `VARCHAR(50)` | 不可空 | — | 报价类型，例如 historical_dataset_price。 |
| `observed_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 已知的原报价时间；未知时为空。 |
| `collected_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 采集或写入该来源记录的时间。 |
| `current_price_verified` | `BOOLEAN` | 不可空 | — | 是否核实为当前价格。 |

- 唯一键：`(source_id, record_key)`。

检查约束：

```sql
amount >= 0
```

### product_sources

逐商品保存外部来源、SKU、许可与原始快照。

模型：`ProductSource`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `source_name` | `TEXT` | 不可空 | — | 来源名称。 |
| `source_sku` | `TEXT` | 不可空 | — | 来源商品编号。 |
| `product_url` | `TEXT` | 可空 | — | 来源商品页地址。 |
| `official_dataset_url` | `TEXT` | 可空 | — | 原始官方数据集地址。 |
| `metadata_mirror_url` | `TEXT` | 可空 | — | 补充元数据镜像地址。 |
| `catalog_date` | `TEXT` | 可空 | — | 来源目录日期描述。 |
| `metadata_license` | `TEXT` | 可空 | — | 来源数据许可信息。 |
| `collected_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 采集或写入该来源记录的时间。 |
| `raw_data` | `JSONB` | 不可空 | — | 标准化记录与原始来源快照 JSONB。 |

- 唯一键：`(source_name, source_sku)`。

### products

商品资料主表，内部 ID 与导入来源身份分离。

模型：`Product`；定义：[源码](../backend/app/database/catalog_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `import_key` | `VARCHAR(150)` | 不可空 | — | 标准素材标识，与内部商品 ID 不同。 |
| `category_id` | `BIGINT` | 不可空 | `categories.id` | 所属商品分类。 |
| `name_original` | `TEXT` | 不可空 | — | 来源原文商品名。 |
| `name_zh` | `TEXT` | 可空 | — | 人工维护的可选中文名。 |
| `brand` | `TEXT` | 可空 | — | 品牌。 |
| `model` | `TEXT` | 可空 | — | 商品型号。 |
| `description_original` | `TEXT` | 不可空 | — | 原文完整介绍。 |
| `introduction_zh` | `TEXT` | 不可空 | — | 中文简要介绍。 |
| `specs` | `JSONB` | 不可空 | — | JSONB 参数，区分来源原文、提取证据和人工确认值。 |
| `quality` | `JSONB` | 不可空 | — | JSONB 资料质量、缺失字段等标记。 |
| `status` | `VARCHAR(20)` | 不可空 | — | 当前业务状态，见本表约束或主文状态说明。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |

- 唯一键：`(import_key)`。

### refund_events

售后处理事件与操作说明。

模型：`RefundEvent`；定义：[源码](../backend/app/database/aftersales_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `refund_id` | `BIGINT` | 不可空 | `refund_requests.id` | 关联退款申请。 |
| `actor_id` | `INTEGER` | 不可空 | `users.id` | 操作人；系统事件可为空。 |
| `action` | `VARCHAR(40)` | 不可空 | — | 处理事件类型。 |
| `note` | `TEXT` | 不可空 | — | 退款处理依据与操作说明。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |

### refund_evidence

私有售后凭证文件路径和归属。

模型：`RefundEvidence`；定义：[源码](../backend/app/database/aftersales_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `refund_id` | `BIGINT` | 可空 | `refund_requests.id` | 关联退款申请。 |
| `storage_key` | `TEXT` | 不可空 | — | 相对素材根目录的文件位置。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |

### refund_requests

退款/退货申请、审核及归还物流。

模型：`RefundRequest`；定义：[源码](../backend/app/database/aftersales_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `chat_session_id` | `BIGINT` | 可空 | `chat_sessions.id` | 关联订单会话，删除会话后允许置空。 |
| `request_key` | `VARCHAR(64)` | 不可空 | — | 客户端幂等请求编号。 |
| `request_hash` | `VARCHAR(64)` | 不可空 | — | 提交内容指纹，防止同一请求键用于不同内容。 |
| `reason` | `VARCHAR(30)` | 不可空 | — | 退款原因代码。 |
| `description` | `TEXT` | 不可空 | — | 客户提交的情况说明。 |
| `contact_phone` | `VARCHAR(30)` | 不可空 | — | 客户确认的售后联系电话。 |
| `received` | `BOOLEAN` | 不可空 | — | 客户是否声明收到货。 |
| `amount` | `NUMERIC(14, 2)` | 不可空 | — | 金额；旧 orders.amount 为浮点型，现行金额字段使用 NUMERIC。 |
| `currency` | `VARCHAR(3)` | 不可空 | — | 金额币种；不自动换汇。 |
| `status` | `VARCHAR(30)` | 不可空 | — | 当前业务状态，见本表约束或主文状态说明。 |
| `route_reason` | `TEXT` | 不可空 | — | 自动处理或人工审核的路由依据。 |
| `original_status` | `VARCHAR(30)` | 不可空 | — | 申请时原订单状态，决定库存/退货处理。 |
| `stock_restored` | `BOOLEAN` | 不可空 | — | 是否已回补库存，防止重复恢复。 |
| `reviewer_id` | `INTEGER` | 可空 | `users.id` | 审核管理员。 |
| `review_note` | `TEXT` | 可空 | — | 审核说明。 |
| `return_address` | `TEXT` | 可空 | — | 审核批准后提供的退货地址。 |
| `return_due_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 建议寄回截止时间。 |
| `return_carrier` | `VARCHAR(100)` | 可空 | — | 退货快递公司。 |
| `return_tracking` | `VARCHAR(100)` | 可空 | — | 退货单号。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |
| `refunded_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 模拟退款完成时间。 |

- 唯一键：`(user_id, request_key)`。
- 唯一索引 `uq_refund_success_order`：`(order_id)`，条件 `status = 'refunded'`。
- 唯一索引 `uq_refund_active_order`：`(order_id)`，条件 `status IN ('review_pending','awaiting_return','return_in_transit')`。

检查约束：

```sql
status IN ('review_pending','awaiting_return','return_in_transit','refunded','rejected','withdrawn')
```

### sale_offers

可购买的演示售价、币种、库存与启用状态。

模型：`SaleOffer`；定义：[源码](../backend/app/database/shop_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `product_id` | `BIGINT` | PK；不可空 | `products.id` | 商品内部 ID。 |
| `price` | `NUMERIC(12, 2)` | 不可空 | — | 演示销售单价。 |
| `currency` | `VARCHAR(3)` | 不可空 | — | 金额币种；不自动换汇。 |
| `stock` | `INTEGER` | 不可空 | — | 演示可用库存，创建订单时预占。 |
| `is_active` | `BOOLEAN` | 不可空 | — | 是否启用购买。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |

检查约束：

```sql
stock >= 0 AND price > 0
```

### shipment_reminders

客户主动催发货记录和管理员跟进结果。

模型：`ShipmentReminder`；定义：[源码](../backend/app/database/aftersales_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `note` | `VARCHAR(500)` | 不可空 | — | 订单或事件说明。 |
| `status` | `VARCHAR(20)` | 不可空 | — | 当前业务状态，见本表约束或主文状态说明。 |
| `handled_note` | `VARCHAR(500)` | 可空 | — | 催发货处理说明。 |
| `handled_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 催发货处理时间。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |

### shipping_addresses

用户可维护的地址簿。

模型：`ShippingAddress`；定义：[源码](../backend/app/database/shop_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `recipient` | `VARCHAR(80)` | 不可空 | — | 收货人。 |
| `phone` | `VARCHAR(30)` | 不可空 | — | 收货联系电话。 |
| `region` | `VARCHAR(200)` | 不可空 | — | 省市区。 |
| `detail` | `VARCHAR(500)` | 不可空 | — | 详细地址。 |
| `postal_code` | `VARCHAR(20)` | 不可空 | — | 邮编。 |
| `is_default` | `BOOLEAN` | 不可空 | — | 是否默认地址。 |

### shop_order_items

订单商品名称、价格、数量与图片快照。

模型：`ShopOrderItem`；定义：[源码](../backend/app/database/shop_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `product_id` | `BIGINT` | 不可空 | `products.id` | 商品内部 ID。 |
| `name` | `TEXT` | 不可空 | — | 下单时商品名称快照。 |
| `image_asset_id` | `BIGINT` | 可空 | `media_assets.id` | 关联媒体资产。 |
| `unit_price` | `NUMERIC(12, 2)` | 不可空 | — | 下单时商品单价快照。 |
| `quantity` | `INTEGER` | 不可空 | — | 商品数量。 |

检查约束：

```sql
quantity BETWEEN 1 AND 99 AND unit_price > 0
```

### shop_orders

现行商城订单及下单时收货地址快照。

模型：`ShopOrder`；定义：[源码](../backend/app/database/shop_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `number` | `VARCHAR(40)` | 不可空 | — | 可展示的唯一订单号，与内部 order_id 不同。 |
| `user_id` | `INTEGER` | 不可空 | `users.id` | 所属用户 ID。 |
| `request_key` | `VARCHAR(64)` | 不可空 | — | 客户端幂等请求编号。 |
| `request_hash` | `VARCHAR(64)` | 不可空 | — | 提交内容指纹，防止同一请求键用于不同内容。 |
| `status` | `VARCHAR(30)` | 不可空 | — | 当前业务状态，见本表约束或主文状态说明。 |
| `total` | `NUMERIC(14, 2)` | 不可空 | — | 订单合计金额。 |
| `currency` | `VARCHAR(3)` | 不可空 | — | 金额币种；不自动换汇。 |
| `shipping_address` | `JSONB` | 不可空 | — | 下单时地址快照 JSONB。 |
| `note` | `TEXT` | 不可空 | — | 订单或事件说明。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 待支付订单截止时间，或分析预览有效期。 |
| `paid_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 模拟支付时间。 |
| `refunded_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 模拟退款完成时间。 |
| `shipped_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 记录发货时间。 |
| `completed_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 用户确认收货时间。 |
| `cancelled_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 取消时间。 |
| `cancel_reason` | `TEXT` | 可空 | — | 取消原因。 |
| `carrier` | `VARCHAR(100)` | 可空 | — | 快递公司。 |
| `tracking_number` | `VARCHAR(100)` | 可空 | — | 快递单号。 |

- 唯一键：`(number)`；`(user_id, request_key)`。

检查约束：

```sql
total > 0
status IN ('pending_payment','paid','shipped','completed','cancelled','refunded')
```

### support_scan_state

历史扫描统计表，当前手动模式保留但不再读写。

模型：`SupportScanState`；定义：[源码](../backend/app/database/support_task_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `scanned_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 历史扫描时间，当前不再更新。 |
| `result` | `JSONB` | 不可空 | — | 历史扫描统计 JSONB。 |

### support_task_events

待办创建、认领、备注、分析与关闭记录。

模型：`SupportTaskEvent`；定义：[源码](../backend/app/database/support_task_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `task_id` | `BIGINT` | 不可空 | `support_tasks.id` | 关联待办。 |
| `actor_id` | `INTEGER` | 可空 | `users.id` | 操作人；系统事件可为空。 |
| `action` | `VARCHAR(30)` | 不可空 | — | 处理事件类型。 |
| `note` | `TEXT` | 不可空 | — | 管理员或系统记录的处理说明。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |

### support_task_previews

未确认建单前的分析预览，30 分钟有效，绑定生成者。

模型：`SupportTaskPreview`；定义：[源码](../backend/app/database/support_task_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `VARCHAR(32)` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `actor_id` | `INTEGER` | 不可空 | `users.id` | 生成预览的管理员；只有本人可确认创建。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `kind` | `VARCHAR(30)` | 不可空 | — | shipping_overdue、receipt_overdue 或 refund_overdue。 |
| `source_key` | `VARCHAR(80)` | 不可空 | — | 业务来源键，例如 paid、shipped、refund:申请ID。 |
| `snapshot` | `JSONB` | 不可空 | — | 当时核实的业务事实和规则建议 JSONB。 |
| `snapshot_version` | `VARCHAR(64)` | 不可空 | — | 事实快照 SHA-256。 |
| `advice` | `JSONB` | 不可空 | — | AI 分析、下一步建议和回复草稿。 |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 待支付订单截止时间，或分析预览有效期。 |

### support_tasks

手动确认创建的订单异常待办。

模型：`SupportTask`；定义：[源码](../backend/app/database/support_task_models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `order_id` | `BIGINT` | 不可空 | `shop_orders.id` | 关联现行 shop_orders 订单。 |
| `kind` | `VARCHAR(30)` | 不可空 | — | shipping_overdue、receipt_overdue 或 refund_overdue。 |
| `source_key` | `VARCHAR(80)` | 不可空 | — | 业务来源键，例如 paid、shipped、refund:申请ID。 |
| `title` | `VARCHAR(160)` | 不可空 | — | 会话或待办标题。 |
| `status` | `VARCHAR(20)` | 不可空 | — | 当前业务状态，见本表约束或主文状态说明。 |
| `priority` | `VARCHAR(10)` | 不可空 | — | 内部优先级。 |
| `assignee_id` | `INTEGER` | 可空 | `users.id` | 认领待办的管理员。 |
| `due_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 对应内部跟进阈值时间，不是承诺交付日期。 |
| `snapshot` | `JSONB` | 不可空 | — | 当时核实的业务事实和规则建议 JSONB。 |
| `snapshot_version` | `VARCHAR(64)` | 不可空 | — | 事实快照 SHA-256。 |
| `advice` | `JSONB` | 不可空 | — | AI 分析、下一步建议和回复草稿。 |
| `advice_version` | `VARCHAR(64)` | 可空 | — | 建议对应的快照指纹。 |
| `analysis_status` | `VARCHAR(20)` | 不可空 | — | pending、generating、ready 或 failed。 |
| `analysis_key` | `VARCHAR(32)` | 可空 | — | 本轮分析请求标识，防止迟到结果覆盖。 |
| `analysis_started_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 分析开始时间，用于在途请求检查。 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 创建或首次记录时间。 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 最后更新时间；部分接口用于版本比较。 |
| `last_seen_at` | `TIMESTAMP WITH TIME ZONE` | 不可空 | — | 该任务最近保存的核实时间；当前没有扫描器更新它。 |
| `resolved_at` | `TIMESTAMP WITH TIME ZONE` | 可空 | — | 人工完成或忽略的时间。 |
| `resolution_note` | `TEXT` | 可空 | — | 关闭待办说明。 |

- 唯一键：`(order_id, kind, source_key)`。

检查约束：

```sql
analysis_status IN ('pending','generating','ready','failed')
kind IN ('shipping_overdue','receipt_overdue','refund_overdue')
status IN ('pending','in_progress','resolved','dismissed')
```

### users

用户、密码哈希和角色。

模型：`User`；定义：[源码](../backend/app/database/models.py)。

| 字段 | PostgreSQL 类型 | 主键 / 可空 | 外键 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | PK；不可空 | — | 数据库主键；预览表使用不可预测的随机字符串。 |
| `username` | `VARCHAR` | 可空 | — | 唯一登录用户名。 |
| `role` | `VARCHAR(20)` | 不可空 | — | 账号角色：user 或 super_admin。 |
| `password_hash` | `VARCHAR` | 可空 | — | bcrypt 密码哈希，不是明文密码。 |
| `created_time` | `TIMESTAMP WITHOUT TIME ZONE` | 可空 | — | 用户创建时间；该字段列类型与多数带时区业务时间不同。 |

- 唯一索引 `ix_users_username`：`(username)`。

## 2 当前 HTTP 接口

共 76 项业务操作，不计 /docs、/redoc、/openapi.json 等框架文档端点。下表按实现文件分组，路径均为挂载后的完整地址。参数、响应 JSON Schema 与是否必填可在运行服务的 `/docs` 中展开查看。

权限：公开表示不要求登录；本人接口要求 JWT 并验证资源归属；管理接口要求数据库当前角色为 super_admin。

### activity.py

[实现文件](../backend/app/api/activity.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/activity/agent-status` | `agent_status` | 登录 / 本人资源 |
| DELETE | `/api/activity/browsing` | `clear_browsing` | 登录 / 本人资源 |
| GET | `/api/activity/browsing` | `browsing` | 登录 / 本人资源 |
| POST | `/api/activity/browsing` | `record_browse` | 登录 / 本人资源 |
| DELETE | `/api/activity/browsing/{entry_id}` | `delete_browse` | 登录 / 本人资源 |
| GET | `/api/activity/sessions` | `sessions` | 登录 / 本人资源 |
| POST | `/api/activity/sessions` | `create_session` | 登录 / 本人资源 |
| DELETE | `/api/activity/sessions/{session_id}` | `delete_session` | 登录 / 本人资源 |
| GET | `/api/activity/sessions/{session_id}` | `messages` | 登录 / 本人资源 |
| POST | `/api/activity/sessions/{session_id}/messages` | `send_message` | 登录 / 本人资源 |
| POST | `/api/activity/sessions/{session_id}/read` | `read_session` | 登录 / 本人资源 |
| GET | `/api/activity/unread` | `unread` | 登录 / 本人资源 |

### admin.py

[实现文件](../backend/app/api/admin.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/admin/homepage` | `get_homepage` | 超级管理员 |
| PUT | `/api/admin/homepage` | `save_homepage` | 超级管理员 |

### admin_products.py

[实现文件](../backend/app/api/admin_products.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/admin/product-categories` | `categories` | 超级管理员 |
| POST | `/api/admin/product-images` | `upload` | 超级管理员 |
| GET | `/api/admin/products` | `products` | 超级管理员 |
| POST | `/api/admin/products` | `create` | 超级管理员 |
| DELETE | `/api/admin/products/{product_id}` | `remove` | 超级管理员 |
| GET | `/api/admin/products/{product_id}` | `detail` | 超级管理员 |
| PUT | `/api/admin/products/{product_id}` | `update` | 超级管理员 |

### aftersales.py

[实现文件](../backend/app/api/aftersales.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/admin/orders/{order_id}/refunds` | `admin_refunds` | 超级管理员 |
| POST | `/api/admin/refunds/{refund_id}/review` | `review` | 超级管理员 |
| POST | `/api/admin/reminders/{reminder_id}/handle` | `handle_reminder` | 超级管理员 |
| POST | `/api/shop/orders/{order_id}/contact` | `contact` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/refund-evidence` | `upload_evidence` | 登录 / 本人资源 |
| GET | `/api/shop/orders/{order_id}/refund-options` | `options` | 登录 / 本人资源 |
| GET | `/api/shop/orders/{order_id}/refunds` | `refunds` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/refunds` | `apply_refund` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/remind-shipping` | `remind` | 登录 / 本人资源 |
| GET | `/api/shop/refund-evidence/{evidence_id}` | `evidence_file` | 凭证本人或超级管理员 |
| POST | `/api/shop/refunds/{refund_id}/return-shipping` | `return_shipping` | 登录 / 本人资源 |
| POST | `/api/shop/refunds/{refund_id}/withdraw` | `withdraw` | 登录 / 本人资源 |

### auth.py

[实现文件](../backend/app/api/auth.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| POST | `/auth/login` | `login` | 公开 |
| GET | `/auth/me` | `me` | 登录 / 本人资源 |
| POST | `/auth/register` | `register` | 公开 |

### catalog.py

[实现文件](../backend/app/api/catalog.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/catalog/categories` | `categories` | 公开 |
| GET | `/api/catalog/home` | `home` | 公开 |
| GET | `/api/catalog/media/{asset_id}` | `media` | 公开 |
| GET | `/api/catalog/products` | `products` | 公开 |
| GET | `/api/catalog/products/{product_id}` | `product_detail` | 公开 |

### human_support.py

[实现文件](../backend/app/api/human_support.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| POST | `/api/activity/sessions/{session_id}/handoff` | `handoff` | 登录 / 本人资源 |
| GET | `/api/admin/support-sessions` | `inbox` | 超级管理员 |
| GET | `/api/admin/support-sessions/unread` | `unread` | 超级管理员 |
| GET | `/api/admin/support-sessions/{session_id}` | `detail` | 超级管理员 |
| POST | `/api/admin/support-sessions/{session_id}/assistant` | `assistant` | 超级管理员 |
| POST | `/api/admin/support-sessions/{session_id}/close` | `close` | 超级管理员 |
| POST | `/api/admin/support-sessions/{session_id}/messages` | `reply` | 超级管理员 |
| POST | `/api/admin/support-sessions/{session_id}/read` | `read_session` | 超级管理员 |

### shop.py

[实现文件](../backend/app/api/shop.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/admin/offers/{product_id}` | `get_offer` | 超级管理员 |
| PUT | `/api/admin/offers/{product_id}` | `set_offer` | 超级管理员 |
| GET | `/api/admin/orders` | `admin_orders` | 超级管理员 |
| POST | `/api/admin/orders/{order_id}/ship` | `ship` | 超级管理员 |
| GET | `/api/shop/addresses` | `addresses` | 登录 / 本人资源 |
| POST | `/api/shop/addresses` | `add_address` | 登录 / 本人资源 |
| DELETE | `/api/shop/addresses/{address_id}` | `delete_address` | 登录 / 本人资源 |
| PUT | `/api/shop/addresses/{address_id}` | `edit_address` | 登录 / 本人资源 |
| GET | `/api/shop/cart` | `cart` | 登录 / 本人资源 |
| POST | `/api/shop/cart` | `add_cart` | 登录 / 本人资源 |
| DELETE | `/api/shop/cart/{item_id}` | `delete_cart` | 登录 / 本人资源 |
| PATCH | `/api/shop/cart/{item_id}` | `update_cart` | 登录 / 本人资源 |
| POST | `/api/shop/checkout/preview` | `preview` | 登录 / 本人资源 |
| GET | `/api/shop/orders` | `orders` | 登录 / 本人资源 |
| POST | `/api/shop/orders` | `checkout` | 登录 / 本人资源 |
| GET | `/api/shop/orders/{order_id}` | `detail` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/cancel` | `cancel` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/complete` | `confirm_receipt` | 登录 / 本人资源 |
| POST | `/api/shop/orders/{order_id}/pay` | `pay` | 登录 / 本人资源 |

### support_tasks.py

[实现文件](../backend/app/api/support_tasks.py)

| 方法 | 路径 | 实现函数 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/admin/support-tasks` | `tasks` | 超级管理员 |
| POST | `/api/admin/support-tasks` | `create` | 超级管理员 |
| POST | `/api/admin/support-tasks/preview` | `preview` | 超级管理员 |
| GET | `/api/admin/support-tasks/summary` | `summary` | 超级管理员 |
| GET | `/api/admin/support-tasks/{task_id}` | `detail` | 超级管理员 |
| POST | `/api/admin/support-tasks/{task_id}/actions` | `action` | 超级管理员 |
| POST | `/api/admin/support-tasks/{task_id}/analyze` | `analyze` | 超级管理员 |
| POST | `/api/admin/support-tasks/{task_id}/conversation` | `conversation` | 超级管理员 |

## 3 关键请求约定

### 手动异常分析与确认创建

第一步：管理员提交选中的内部订单 ID。只返回分析预览，不创建待办。

```http
POST /api/admin/support-tasks/preview
Authorization: Bearer <token>
Content-Type: application/json

{"order_id": 123}
```

有候选事项时，响应 `candidates` 中包含 `preview_id`、`snapshot`、`advice` 和可能已有的 `existing_task_id`。没有符合规则的事项时，candidates 为空。

第二步：管理员确认后，只提交服务端返回的预览编号。

```http
POST /api/admin/support-tasks
Authorization: Bearer <token>
Content-Type: application/json

{"preview_id": "服务端返回的32位十六进制编号"}
```

服务端校验归属、30 分钟有效期和当前事实；响应 `created` 表示是否新建。重复确认同一来源不会重复创建；订单事实变化返回 409。不能让客户端提交模型建议来替代服务端预览。

### 已读确认

会话详情返回 `read_through`。前端确认可见且聚焦后，将该时间原样提交至客户或管理员对应的 `/read` 接口。读取 GET 接口本身不自动清除未读。

```json
{"read_through": "从会话详情取得的带时区时间"}
```

### 常见状态码

| 状态码 | 项目中的常见含义 |
| --- | --- |
| 200 / 201 / 204 | 查询成功、创建成功、删除或无正文操作成功 |
| 202 | 原消息生成仍在进行，重复请求返回在途状态 |
| 400 | 例如重复用户名等业务输入问题 |
| 401 | 未登录、Token 无效或过期 |
| 403 | 普通用户访问管理能力 |
| 404 | 资源不存在，或不属于当前用户 |
| 409 | 状态不允许、库存/版本冲突、请求编号内容不一致、分析事实已变化 |
| 422 | 参数校验或业务必填条件不满足 |
| 503 | 模型、商品数据库查询或配置暂不可用等明确的服务错误 |

不同 API 的具体状态码以实现和 OpenAPI 为准，不能只按 HTTP 方法推断。
