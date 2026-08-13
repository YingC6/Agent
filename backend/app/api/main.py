"""FastAPI主应用"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..config import get_settings, validate_config, print_config
from ..database import init_db
from ..services.logging_config import setup_logging
from .routes import auth, checklists, community, conversations, knowledge, logs, preferences, trip, trips, poi, map as map_routes

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version, description="基于HelloAgents框架的智能旅行规划助手API", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(CORSMiddleware, allow_origins=settings.get_cors_origins_list(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router, prefix="/api")
app.include_router(trip.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(poi.router, prefix="/api")
app.include_router(map_routes.router, prefix="/api")
app.include_router(community.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(checklists.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    setup_logging(settings.log_level)
    init_db()
    print("\n" + "=" * 60)
    print(f"🚀 {settings.app_name} v{settings.app_version}")
    print("=" * 60)
    print_config()
    try:
        validate_config()
        print("\n✅ 配置验证通过")
    except ValueError as e:
        print(f"\n❌ 配置验证失败:\n{e}")
        print("\n请检查.env文件并确保所有必要的配置项都已设置")
        raise
    print("\n" + "=" * 60)
    print("📚 API文档: http://localhost:8000/docs")
    print("📖 ReDoc文档: http://localhost:8000/redoc")
    print("=" * 60 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    print("\n" + "=" * 60)
    print("👋 应用正在关闭...")
    print("=" * 60 + "\n")


@app.get("/")
async def root():
    return {"name": settings.app_name, "version": settings.app_version, "status": "running", "docs": "/docs", "redoc": "/redoc"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.main:app", host=settings.host, port=settings.port, reload=True)
