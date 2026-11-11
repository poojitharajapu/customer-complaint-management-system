"""FastAPI application assembly; routers and services own endpoint behavior."""

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
import uvicorn

from backend.config import APP_DESCRIPTION, APP_TITLE, APP_VERSION, HOST, PORT
from backend.database import check_database_ready
from backend.dependencies import get_db
from backend.routers import agents, complaints, customers, dashboard, messages, outcomes, slas


def create_app() -> FastAPI:
    """Create an app without mutating the database schema during startup."""
    app = FastAPI(title=APP_TITLE, description=APP_DESCRIPTION, version=APP_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "The request conflicts with existing data or database constraints."})

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=500, content={"detail": "A database operation failed."})

    app.include_router(customers.router, prefix="/api/v1")
    app.include_router(complaints.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(slas.router, prefix="/api/v1")
    app.include_router(outcomes.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")

    @app.get("/", tags=["Health"], name="service_root")
    def root():
        return {"message": "Complaint Management System API is running", "status": "healthy"}

    @app.get("/health", tags=["Health"], name="health_check")
    def health():
        return {"status": "healthy", "service": APP_TITLE, "version": APP_VERSION}

    @app.get("/ready", tags=["Health"], name="readiness_check")
    def ready(db: Session = Depends(get_db)):
        check_database_ready(db)
        return {"status": "ready", "database": "available"}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
