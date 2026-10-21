# ServAI 智能客服商城实战项目

项目基于 React、FastAPI、PostgreSQL、LangGraph 与 DeepSeek，包含日常电子商品展示、演示购物和售后、客户多 Agent 咨询、管理员人工接待、客服助手与手动订单异常待办。

## 技术文档

1. [系统技术说明](docs/PROJECT_TECHNICAL_GUIDE.md)：架构、技术栈、目录、业务流程、Agent、配置与运行方式。
2. [逐文件代码说明](docs/CODE_FILE_REFERENCE.md)：129 个第一方源码与配置代码文件的功能及历史文件标记。
3. [数据库与接口参考](docs/DATABASE_AND_API_REFERENCE.md)：26 个 ORM 表的字段、关系和 76 项业务 HTTP 操作。

专项说明位于 [backend/scripts](backend/scripts)，素材采集说明位于 [product_materials/README.md](product_materials/README.md)。

当前订单异常流程由管理员手动发起分析并确认创建待办，不运行后台自动扫单。支付、库存和退款均为演示业务。
