from __future__ import annotations

from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.gzip import GZipMiddleware

from .config import get_settings
from .db import DatabaseManager
from .schemas import DiagnosisSupportBatchRequest, DiagnosisSupportRequest, ResponsibilityRequest, StatisticsRequest
from .services import run_diagnosis_support, run_diagnosis_support_batch, run_responsibility, run_statistics


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("server_maximo.app")
settings = get_settings()

def require_token(x_vita_token: str | None = Header(default=None)) -> None:
    if settings.api_token and x_vita_token != settings.api_token:
        raise HTTPException(status_code=401, detail="接口令牌无效")


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ConnectionError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        DatabaseManager.initialize_oracle_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Oracle client init skipped: %s", exc)
    yield


app = FastAPI(title="VITA Maximo 服务", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=512)


@app.get("/healthz")
def healthz(_: None = Depends(require_token)) -> dict[str, object]:
    db_ready, db_message = DatabaseManager.check_ready()
    return {
        "status": "ok",
        "db_available": db_ready,
        "db_message": db_message,
        "dsn": settings.db_dsn,
    }


@app.post("/statistics/run")
def statistics_endpoint(request: StatisticsRequest, _: None = Depends(require_token)) -> dict[str, object]:
    try:
        return run_statistics(request.entities, request.query_type)
    except Exception as exc:  # noqa: BLE001
        raise _as_http_error(exc) from exc


@app.post("/responsibility/run")
def responsibility_endpoint(request: ResponsibilityRequest, _: None = Depends(require_token)) -> dict[str, object]:
    try:
        return run_responsibility(request.entities)
    except Exception as exc:  # noqa: BLE001
        raise _as_http_error(exc) from exc


@app.post("/diagnosis/support")
def diagnosis_support_endpoint(request: DiagnosisSupportRequest, _: None = Depends(require_token)) -> dict[str, object]:
    try:
        return run_diagnosis_support(
            user_query=request.user_query,
            entities_payload=request.entities,
            vector_candidate_ids=request.vector_candidate_ids,
            limit=request.limit,
        )
    except Exception as exc:  # noqa: BLE001
        raise _as_http_error(exc) from exc


@app.post("/diagnosis/support-batch")
def diagnosis_support_batch_endpoint(request: DiagnosisSupportBatchRequest, _: None = Depends(require_token)) -> dict[str, object]:
    try:
        return run_diagnosis_support_batch(user_query=request.user_query, layers=request.layers)
    except Exception as exc:  # noqa: BLE001
        raise _as_http_error(exc) from exc


if __name__ == "__main__":
    uvicorn.run("server_maximo.app:app", host=settings.host, port=settings.port, reload=False)
