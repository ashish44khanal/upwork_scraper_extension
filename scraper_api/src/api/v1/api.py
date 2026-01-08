from fastapi import APIRouter
from src.api.v1.endpoints import health, scrape

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(scrape.router, prefix="/scrape", tags=["scrape"])
