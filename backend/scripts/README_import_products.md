# 商品素材 PostgreSQL 导入脚本

从项目根目录运行，使用已有后端虚拟环境：

```powershell
# 先检查 400 条记录、原始来源文件、图片大小和 SHA-256，不连接数据库
.\backend\venv\Scripts\python.exe .\backend\scripts\import_products.py --check-only

# 校验通过后，创建所需商品表并在一个事务中导入
.\backend\venv\Scripts\python.exe .\backend\scripts\import_products.py
```

脚本默认读取项目中的 `product_materials/products.jsonl` 和同目录下的图片、原始来源文件；默认路径以脚本位置计算，从其他工作目录执行也有效。不会下载图片、导入 rejected_candidates 或改变前端数据。

## 数据库连接

优先读取环境变量 `DATABASE_URL`，其次读取 `backend/.env` 中同名变量；未设置时沿用 `app/database/database.py` 中现有连接。目标数据库必须预先存在，且账号有建表和写入权限。脚本不会创建数据库。

可在 `backend/.env` 添加：

```dotenv
DATABASE_URL=postgresql+psycopg2://用户名:密码@localhost:5432/customer_service
```

这里的用户名、密码是占位说明，替换为自己的连接配置；密码中的 URL 特殊字符需要 URL 编码。不要把真实连接串写进版本库或终端截图。

依赖已加入 `backend/requirements.txt`，使用新环境时先安装：

```powershell
.\backend\venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

## 创建的六张表

| 表 | 作用 | 此批素材全新导入后的数量 |
| --- | --- | --- |
| categories | 分类代码、名称和可选父分类 | 12 |
| products | 内部 ID、导入标识、名称、品牌、介绍、JSONB 参数和质量信息 | 400 |
| media_assets | 以图片 SHA-256 去重的文件元数据 | 395 |
| product_sources | 来源名称与 SKU、地址、时间、许可、原始资料 JSONB | 400 |
| product_images | 商品与图片关联、主图、排序、逐条图片来源与授权状态 | 400 |
| product_price_records | 历史金额、币种、价格类型、原报价时间和采集时间 | 400 |

脚本只创建这六张不存在的商品表，不创建或改写 users/orders。若已存在同名表，`create_all` 不会自动迁移表结构；结构不兼容时事务失败，需要先做迁移。

## 字段与重复执行行为

- 商品内部 ID 使用数据库自增主键。源 `id`（例如 bb-1126038）写入 `products.import_key`。
- 分类按 code 更新；来源以 `(source_name, source_sku)` 唯一。重复导入根据来源 SKU 找回同一个内部商品 ID。
- 更新名称原文、品牌、型号、原文介绍、中文摘要、原始参数、提取参数、质量信息和来源快照。人工编辑的 `name_zh`、商品状态及 `specs.verified` 保留。
- 原始 `specifications_original` 放入 `specs.source_original`，`extracted_attributes` 放入 `specs.extracted`。它们不会自动成为已确认参数。
- `raw_data.standardized` 保存整条标准化记录，`raw_data.original` 保存对应 source_original.json，许可与图片授权状态均保留。
- 图片文件本体继续放在素材目录，数据库只存相对 `storage_key`。文件内容相同的多个商品共用一条 media_assets；首次运行不修改或复制原图文件。
- 每次替换当前来源的图片关联，保留其他来源的图片关联。若其他来源已有主图，则不覆盖其主图；否则以当前来源第一张图为主图。关联表 ID 可能在重跑时变化，不应作为外部稳定标识；商品 ID、来源 ID 和资源 ID 保持稳定。
- 所有导入商品默认为 draft，导入不会将商品标为在售。
- 历史价格使用 NUMERIC(12,2)，USD 不换算成人民币。observed_at 未知时保留 NULL，不用 collected_at 冒充报价时间。
- 价格按来源和“金额、币种、价格类型、原报价时间”的确定性指纹去重。重跑同一素材不增加价格行；修改金额会追加历史记录，而不会把旧金额覆盖成当前售价。原报价时间未知且其他价格字段相同的记录会合并。
- 不删除输入批次之外的商品，也不清理失去关联的旧图片资产。

## 事务与失败处理

完整批次在写库前完成本地校验，缺图、哈希不符、原始来源缺失、重复 SKU、币种/金额不合法、时间无时区或素材路径越界都会阻止导入。

创建商品表和全部写入位于同一个 PostgreSQL 事务中，任何数据库操作失败都会回滚这一批。输出计数表示本次处理数量，而不是新增数量。并发脚本使用事务级 advisory lock 串行导入，避免重复创建和主图冲突；等待锁超过 15 秒会失败并回滚。

## 其他素材位置

```powershell
.\backend\venv\Scripts\python.exe .\backend\scripts\import_products.py `
  --input 'D:\materials\products.jsonl' `
  --materials-root 'D:\materials'
```

自定义素材需要沿用当前 JSONL 字段和相对目录结构。需要执行原始资料追溯，所以 source_original.json 也是必需输入。

## 验证脚本

```powershell
# 仅文件校验和异常输入测试
.\backend\venv\Scripts\python.exe -m unittest discover -s .\backend\tests -p test_product_import.py -v

# PostgreSQL 集成测试：隔离测试 schema，全部操作最终回滚
$env:CATALOG_PG_TEST = '1'
.\backend\venv\Scripts\python.exe -m unittest discover -s .\backend\tests -p test_product_import.py -v
Remove-Item Env:CATALOG_PG_TEST
```

集成测试已验证：400 条真实素材导入；重复导入后六张表数量不变；已审阅参数、人工翻译名称和商品状态保留；一条主图/商品；原报价时间保持 NULL；中途写入失败后回滚；测试 schema 和测试记录最终消失。不会向现有商品表提交测试数据。
