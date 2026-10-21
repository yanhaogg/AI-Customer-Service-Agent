from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.admin import router as admin_router
from app.api.admin_products import router as admin_products_router
from app.api.shop import router as shop_router, admin_router as shop_admin_router
from app.api.activity import router as activity_router
from app.api.aftersales import router as aftersales_router,admin_router as aftersales_admin_router
from app.api.human_support import router as human_admin_router,user_router as human_user_router
from app.api.support_tasks import router as support_tasks_router


server = FastAPI()
server.include_router(support_tasks_router)
server.include_router(catalog_router)
server.include_router(admin_router)
server.include_router(admin_products_router)
server.include_router(activity_router)
server.include_router(shop_router)
server.include_router(shop_admin_router)
server.include_router(aftersales_router)
server.include_router(aftersales_admin_router)
server.include_router(human_admin_router)
server.include_router(human_user_router)
server.include_router(
    auth_router,
    prefix="/auth"
)#注册Router到FastAPI

'''
接口
POST /auth/register
POST /auth/login
'''

# 解决React跨域
server.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)
