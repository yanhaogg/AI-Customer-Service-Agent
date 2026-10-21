# 历史文件命名说明

`legacy_` 前缀表示早期保留文件，当前运行链路没有使用。文件内容保留用于回顾，不代表其旧接口仍然可运行。没有此前缀也不代表一定是应用入口，应结合逐文件说明阅读。

## 已标记的文件

| 原路径 | 当前路径 | 原因 |
| --- | --- | --- |
| `backend/test.py` | [backend/legacy_refund_demo.py](../backend/legacy_refund_demo.py) | 早期退款脚本，引用的 graph.app 已不再存在 |
| `frontend/src/App.jsx` | [frontend/src/legacy_App.jsx](../frontend/src/legacy_App.jsx) | 旧示例页面，main.jsx 当前挂载的是 Router |
| `frontend/src/App.css` | [frontend/src/legacy_App.css](../frontend/src/legacy_App.css) | 旧 App 的模板样式 |
| `frontend/src/data/products.js` | [frontend/src/data/legacy_products.js](../frontend/src/data/legacy_products.js) | 早期虚构商品，已替换为数据库目录 |
| `frontend/src/api/request.js` | [frontend/src/api/legacy_request.js](../frontend/src/api/legacy_request.js) | 旧请求封装，当前页面使用 lib 中的实现 |
| `frontend/src/components/ProtectedRoute.jsx` | [frontend/src/components/legacy_ProtectedRoute.jsx](../frontend/src/components/legacy_ProtectedRoute.jsx) | 当前路由未引用的旧权限包装 |
| `frontend/src/components/ProductVisual.jsx` | [frontend/src/components/legacy_ProductVisual.jsx](../frontend/src/components/legacy_ProductVisual.jsx) | 旧商品示意图，已使用真实商品图片 |
| `frontend/src/assets/react.svg` | [frontend/src/assets/legacy_react.svg](../frontend/src/assets/legacy_react.svg) | 旧 React 模板图标 |
| `frontend/src/assets/vite.svg` | [frontend/src/assets/legacy_vite.svg](../frontend/src/assets/legacy_vite.svg) | 旧 Vite 模板图标 |
| `frontend/public/icons.svg` | [frontend/public/legacy_icons.svg](../frontend/public/legacy_icons.svg) | 旧示例页图标集合 |
| `frontend/README.md` | [frontend/legacy_README.md](../frontend/legacy_README.md) | Vite 模板说明，现行文档位于 docs |

## 保持原名的文件

- `backend/app/database/models.py`：User 仍被认证和全部业务使用。仅在旧 Order 类旁增加 LEGACY 注释，保留原表和类名。
- `backend/app/agent/nodes.py`、`tools.py`：兼容转导出入口，职责已经在技术文档注明，继续保留兼容路径。
- `frontend/src/pages/Chat.jsx`、`Orders.jsx`：当前路由正在使用的转导出入口，不是废弃页面。
- `frontend/src/main.jsx`、`index.css`：仍是当前入口和全局样式，即使含早期片段也不能整体标记为废弃。
- 数据库历史表、依赖清单、锁文件和采集素材没有重命名；它们不等同于未使用的历史业务源码。

现行实现和阅读顺序见 [系统技术说明](PROJECT_TECHNICAL_GUIDE.md)，完整文件清单见 [逐文件代码说明](CODE_FILE_REFERENCE.md)。
