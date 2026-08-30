from sys import prefix

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.config.database import engine
from app.models import Base
from app.routes import (
    auth,
    categories,
    products,
    suppliers,
    purchases,
    sales,
    stock,
    businesses,
    product_imports,
    inventory,
    inventory_counts,
    reports,
    briefings,
    dashboard,
    intelligence,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0")

origins = [
    origin.strip()
    for origin in settings.ALLOWED_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(products.router, prefix=settings.API_V1_STR, tags=["products"])
app.include_router(suppliers.router, prefix=settings.API_V1_STR, tags=["suppliers"])
app.include_router(purchases.router, prefix=settings.API_V1_STR, tags=["purchases"])
app.include_router(sales.router, prefix=settings.API_V1_STR, tags=["sales"])
app.include_router(stock.router, prefix=settings.API_V1_STR, tags=["stock"])
app.include_router(businesses.router, prefix=settings.API_V1_STR, tags=["businesses"])
app.include_router(product_imports.router, prefix=settings.API_V1_STR, tags=["product import"])
app.include_router(categories.router, prefix=settings.API_V1_STR, tags=["categories"])
app.include_router(inventory.router, prefix=settings.API_V1_STR, tags=["inventory"])
app.include_router(inventory_counts.router, prefix=settings.API_V1_STR, tags=["inventory-counts"])
app.include_router(reports.router, prefix=settings.API_V1_STR, tags=["reports"])
app.include_router(briefings.router, prefix=settings.API_V1_STR, tags=["briefings"])
app.include_router(dashboard.router, prefix=settings.API_V1_STR, tags=["dashboard"])
app.include_router(
    intelligence.router,
    prefix=settings.API_V1_STR,
    tags=["intelligence"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
