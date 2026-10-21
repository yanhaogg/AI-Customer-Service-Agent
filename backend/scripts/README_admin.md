# 超级管理员与首页选品

本地已创建账号 `superadmin`。初始密码保存在 `backend/.superadmin_credentials.txt`，该文件已加入 Git 忽略列表，请妥善保管。

在 http://127.0.0.1:5173/login 登录后，导航栏会出现“首页管理”，进入 http://127.0.0.1:5173/admin/homepage 选品并保存。

- 主推商品：1 个。
- 侧栏商品：最多 2 个。
- 推荐商品：最多 8 个，可以调整顺序。
- 同一商品不能同时出现在多个位置。

保存后，首页接口从 PostgreSQL 的 `homepage_config` 表读取配置；刷新首页即可看到变化。尚未保存配置时继续使用原有默认选品规则。多人同时修改时，后保存的旧版本会被拒绝，需要重新加载再编辑。

## 创建其他管理员

只能在可信后端主机运行本地命令。在项目根目录执行：

```powershell
& backend/venv/Scripts/python.exe backend/scripts/create_superadmin.py --username another_admin
```

命令交互输入并确认密码（至少 12 个字符）；密码不会出现在命令行历史中。命令拒绝覆盖已有账号或将已有普通账号自动提升权限。也支持 `--generate-password --credentials-file <新文件路径>` 生成随机密码。

脚本会自动补充 `users.role` 字段并创建 `homepage_config` 表。已有用户默认保持 `user`。新环境也可以运行 `backend/app/database/init_db.py` 完成建表，前提是配置好数据库连接并准备商品表。

## 权限边界

公开 `/auth/register` 只创建 `user`，提交 `role` 等额外字段会返回 422。不存在公开的管理员注册接口。

前端依据 `/auth/me` 返回的数据库角色展示入口，普通用户直接进入管理地址也看不到编辑控件。所有 `/api/admin` 接口另外验证 JWT 和数据库中的当前角色：未登录返回 401，普通用户返回 403；修改浏览器缓存或令牌中的角色不能获得权限。

首页配置接口为 `GET/PUT /api/admin/homepage`，保存时需要携带当前 `revision`，版本冲突返回 409。

## 商品管理

超级管理员登录后进入 http://127.0.0.1:5173/admin/products，或点击导航栏“商品管理”。支持按名称、品牌、型号搜索和分类筛选，以及新增、编辑、删除商品。

编辑字段包含分类、原文名称、中文名称、品牌型号、中文介绍、原文详细介绍、参数和参考价格。参数按 `名称=值` 每行一个填写，会保存到 `specs.verified`；导入的原始参数和提取证据继续保留。价格变更会新增参考价记录，保留旧价格；已有价格不能清空。

支持上传不超过 5MB 的 JPEG、PNG、WebP（最多 2000 万像素）。后端验证并转换成 JPEG，保存在 `product_materials/admin_uploads/`，图片元数据存入 `media_assets`，不会将原始上传文件作为可执行内容提供。相同图片去重存储；备份时需同时备份数据库和素材目录。上传成功后需保存商品，才能关联到商品。

删除使用逻辑删除（`products.status = deleted`），公开列表、详情、首页和管理列表均不再展示该商品，原始资料、价格、图片资产保留。删除首页推荐会同步移除选品；删除首页主推会自动选择其他可展示商品，其他选品尽量保留。

管理接口（均要求数据库当前角色为 `super_admin`）：

- `GET /api/admin/product-categories`：分类。
- `GET/POST /api/admin/products`：分页检索、新增。
- `GET/PUT/DELETE /api/admin/products/{id}`：详情、编辑、逻辑删除。
- `POST /api/admin/product-images`：验证并存储图片（JSON base64）。

编辑时需携带读取时的 `updated_at`，版本冲突返回 409，需要重新读取后编辑。前端隐藏普通用户的入口和控件，后端独立校验所有读写与上传接口，普通用户返回 403，未登录返回 401。
