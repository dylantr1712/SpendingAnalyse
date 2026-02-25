from fastapi import APIRouter

from app.api.routes import auth, import_routes, dashboard, review_queue, merchant_map, transactions, goals, profile

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(import_routes.router, prefix="/import", tags=["import"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(review_queue.router, prefix="/review-queue", tags=["review_queue"])
api_router.include_router(merchant_map.router, prefix="/merchant-map", tags=["merchant_map"])
api_router.include_router(transactions.router, prefix="/transaction", tags=["transaction"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
