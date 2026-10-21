# 日常电子产品素材库

本目录为 ServAI 项目收集的本地开发素材，未连接项目数据库，也未改动当前前端商品数据。原始资料来自 Best Buy 历史商品目录及 Algolia 公开示例目录，图片从对应 Best Buy 商品图片地址下载。收集时间与逐条来源见 JSON。

## 怎么看

- 打开 `gallery.html`：离线查看图片、中文摘要和英文介绍，可按分类或关键词筛选。
- 查看 `products.json`：全部标准化商品记录。
- 查看 `products.jsonl`：一行一条记录，便于后续批量导入数据库。
- 查看 `collection_report.json` 和 `validation_report.json`：收集数量、各分类数量、图片校验和失败记录。
- 查看 `preview_contact_sheet.jpg`：每类两张商品图的抽样拼图。

## 分类和单条素材结构

商品按 `categories/<分类>/<商品ID>/` 存放：

```text
product_materials/
  categories/
    01_phones/                 手机
    02_computers/              笔记本与台式电脑
    03_tablets/                平板电脑
    04_monitors/               显示器
    05_audio/                  耳机与音箱
    06_wearables/              智能穿戴
    07_smart_home/             智能家居
    08_cameras/                相机与摄像机
    09_networking/             路由器与网络设备
    10_storage/                存储设备
    11_power/                  充电与电源配件
    12_peripherals/            键鼠与电脑外设
      bb-<SKU>/
        main.jpg              已下载且解码校验的商品图片
        image_metadata.json   图片地址、尺寸、SHA-256、下载时间
        product.json          标准化商品信息
        introduction.txt      中文简要介绍
        introduction.md       中文简介、英文原文、原始参数和来源
        source_original.json  未覆盖的源记录（两个数据源分开保存）
  products.json
  products.jsonl
  product.schema.json
  gallery.html
  collection_report.json
  validation_report.json
  preview_contact_sheet.jpg
  sources/                    数据源快照与许可说明
  scripts/                    收集与校验脚本
```

## 信息处理规则

1. 商品 ID 以 Best Buy SKU 为基础，每条独立 SKU 唯一；不同配色或运营商版本可能是同一型号的不同 SKU，不宣称全部为不同型号。
2. 商品名称、品牌、原始英文介绍、型号、UPC、类型、原分类均按来源保留。不是虚构产品，也没有替换成 ServAI 自有品牌。
3. 所有金额保留为 **历史 USD 价格**，没有换算成人民币，也不是实时售价、库存或购买承诺。
4. `specifications_original` 保存原目录的明确参数；`extracted_attributes` 是从名称和介绍中匹配的尺寸、容量、分辨率、接口等片段，每项带有原文证据。提及的规格不一定都是该产品本体的规格，应结合上下文使用。例如配件支持的设备规格不能直接写成配件本身规格。
5. 中文简介为根据分类和明确原文片段整理的**规则摘要**，不是逐字翻译或厂家官方中文文案。英文原文完整保留，便于以后使用翻译服务或人工润色。
6. 参数缺失时保留 null 或空对象，并写入 `quality.missing_fields`。CPU、材质、续航、保修等未在来源明确提供的参数不补造。
7. 每条保留一张本地主图。只有能够下载并被 Pillow 完整解码、宽高均不少于 100 像素且通过占位图筛查的图片才进入最终汇总；下载失败候选见收集报告，不混入有效商品数。
8. 这批是历史素材，不保证链接仍指向在售商品；没有进行逐项厂商官网的当前参数核验。

## 后续数据库映射建议

- 商品表：`id`、`source_sku`、`name_original`、`brand`、`model`、`description_original`、`introduction_zh`、价格金额/币种/类型、`category_id`。
- 分类表：`category_id`、`category_name_zh`。
- 图片表：商品 ID、`local_path`、来源 URL、SHA-256、宽高、授权状态。
- 参数表：原始参数 JSON、提取字段 JSON（保留证据字段）。
- 来源表：来源 URL、收集时间、许可标记、原始记录路径。
- 图片相对路径基于本目录，导入数据库时按部署位置转换；原始资料和价格历史属性不要丢弃。

## 来源与使用范围

- 官方资料：[Best Buy API Playground](https://github.com/BestBuy/api-playground)。官方 README 明确说明使用历史目录，仅用于教学和训练；源数据记录创建时间为 2016 年。
- 详情文案补充来源：[Algolia e-commerce 示例数据集](https://github.com/algolia/datasets/tree/master/ecommerce)。保存独立镜像标记，不把镜像文案冒充官方最新资料。
- 官方数据许可：[CC BY-NC 4.0](https://github.com/BestBuy/api-playground/blob/master/LICENSE-DATASET.md)，本目录保存原许可全文及官方 README。数据的非商业与署名要求需要随导入一同保留。
- Algolia 镜像文案和第三方商品图片未获得单独商业授权，不推定官方数据许可覆盖这些内容。图片逐条记录 `rights_status`；用于商业商城前需要替换或另行获得授权。
- 中文摘要、中文分类、字段标准化、图片下载/校验是本项目新增处理；英文资料仍属于原来源。

## 重建与检查

需要 Python 3、Pillow 和 jsonschema（见 scripts/requirements.txt）。先准备 `sources/bestbuy_complete.sqlite` 和 `sources/algolia_records.json`，从项目根目录运行：

```text
python product_materials/scripts/collect.py
python product_materials/scripts/finalize_text.py
python product_materials/scripts/verify_and_preview.py
```

收集脚本可复用已验证图片，最终数量不足 400 会返回失败，避免把未完成任务记为完成。官方数据下载脚本为 `scripts/download_source.py`，仅使用公开 HTTP 下载和标准库，不启动第三方服务。


## 本次收集结果（2026-10-14）

有效记录 **400 条（400 个独立 SKU）**，本地主图 **400 个文件、395 个不同图像哈希**。已剔除 Image Unavailable 占位图并完成图片全量解码校验，最终无占位图。

238 条匹配到官方目录中的型号等原始字段；302 条有带原文证据的参数片段；其余缺失字段没有补造。不同配色/版本可能共享商品图，因此不宣称 400 个不同型号或 400 张完全不同的图。

分类数量：手机 35；笔记本与台式电脑 45；平板电脑 30；显示器 20；耳机与音箱 75；智能穿戴 30；智能家居 25；相机与摄像机 30；路由器与网络设备 20；存储设备 25；充电与电源配件 25；键鼠与电脑外设 40。

未进入最终库的候选文件移至 `sources/rejected_candidates/`，仅用于排查下载与占位图问题；数据库导入以根目录的 `products.jsonl` 为准，不导入该目录。下载失败的候选原因另见 collection_report.json。
