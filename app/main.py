from sys import prefix

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.config.database import engine
from app.models import Base
from app.routes import auth, products, suppliers, purchases, sales, stock, businesses, transactions

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
app.include_router(transactions.router, prefix=settings.API_V1_STR, tags=["transactions"])

@app.get("/health")
async def health():
    return {"status": "ok"}