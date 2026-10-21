# 数据库商品展示

首页、全部商品页和详情页通过 `/api/catalog` 读取 PostgreSQL，不再使用前端 `src/data/products.js` 的演示商品。

从项目根目录启动后端：

```powershell
.\backend\venv\Scripts\python.exe -m uvicorn app.main:server --app-dir backend --reload --host 127.0.0.1 --port 8000
```

前端沿用 Vite 开发服务，`/api/catalog` 自动代理到 `http://127.0.0.1:8000`。先确保运行过商品导入脚本，数据库中存在六张商品表和商品记录。

接口：

- `GET /api/catalog/home`：首页精选、跨分类推荐、分类数量。
- `GET /api/catalog/categories`：数据库分类与商品数量。
- `GET /api/catalog/products?category=05_audio&q=Marshall&sort=price_asc&page=1&page_size=24`：分页、分类、搜索、排序。
- `GET /api/catalog/products/{id}`：商品详情、原文参数和同类商品。
- `GET /api/catalog/media/{asset_id}`：按数据库图片资源 ID 读取本地文件，不公开整个素材目录。

`DATABASE_URL` 支持环境变量和 `backend/.env`，后端与导入脚本使用同一配置。图片默认位于项目的 `product_materials`；换目录时设置 `PRODUCT_MATERIALS_ROOT` 为素材库绝对路径，保留数据库中 storage_key 对应的相对结构。

页面使用数据库内部商品 ID。多件商品共享图片资产不会影响各自详情页。name_zh 为空时展示原始名称；金额按数据库的原币种显示，并明确标为历史参考价。

这是本地商品资料展示，包含已导入的 draft/reviewed/published 记录，未提供购买接口。生产商城可在发布流程完成后将可见范围限制为 published；这里不会自动修改商品状态。

生产前端需要同域反向代理 `/api/catalog`，或在构建前设置 `VITE_API_BASE_URL` 为后端地址，并配置允许的跨域来源。没有连上服务或没有商品时，页面会显示错误或空状态，不使用旧演示商品兜底。

验证接口（只读当前已导入库）：

```powershell
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_catalog_api.py -v
```
