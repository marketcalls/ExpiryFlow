import logging

from fastapi import APIRouter, HTTPException

from dependencies import ActiveSessionDep, DbDep, DuckDbDep
from duckdb_manager import DUCKDB_PATH
from models import ApiConfig
from schemas import (
    DownloadHistoryItem,
    DownloadHistoryResponse,
    DownloadProgress,
    DownloadRequest,
    MessageResponse,
    RateLimitStatus,
)
from services.download_service import (
    cancel_job,
    create_job,
    get_active_jobs,
    get_download_history,
    get_job,
    rate_limiter,
    start_download_thread,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("/start", response_model=DownloadProgress)
def start_download(
    data: DownloadRequest,
    session: ActiveSessionDep,
    db: DbDep,
    duck: DuckDbDep,
) -> DownloadProgress:
    config = db.query(ApiConfig).first()
    if not config:
        raise HTTPException(status_code=400, detail="No API configuration found.")

    option_types = ["CE", "PE"] if data.option_type.upper() == "BOTH" else [data.option_type.upper()]

    job_id = create_job()
    start_download_thread(
        job_id=job_id,
        underlying_scrip=data.underlying_scrip,
        exchange_segment=data.exchange_segment,
        instrument=data.instrument,
        security_id=data.security_id,
        option_types=option_types,
        expiry_flags=data.expiry_flags,
        expiry_codes=data.expiry_codes,
        strike_range=data.strike_range,
        interval=data.interval,
        from_date=data.from_date,
        to_date=data.to_date,
        access_token=session.access_token,
        client_id=session.dhan_client_id,
        duckdb_path=str(DUCKDB_PATH),
    )
    logger.info("Download job %s started for %s", job_id, data.underlying_scrip)
    return DownloadProgress(**get_job(job_id))


@router.get("/{job_id}/progress", response_model=DownloadProgress)
def download_progress(job_id: str, session: ActiveSessionDep) -> DownloadProgress:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return DownloadProgress(**job)


@router.post("/{job_id}/cancel", response_model=MessageResponse)
def cancel_download(job_id: str, session: ActiveSessionDep) -> MessageResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cancel_job(job_id)
    return MessageResponse(message="Cancellation requested")


@router.get("/active", response_model=list[DownloadProgress])
def active_downloads(session: ActiveSessionDep) -> list[DownloadProgress]:
    return [DownloadProgress(**j) for j in get_active_jobs()]


@router.get("/history", response_model=DownloadHistoryResponse)
def download_history(session: ActiveSessionDep, duck: DuckDbDep) -> DownloadHistoryResponse:
    items = get_download_history(duck)
    return DownloadHistoryResponse(
        items=[DownloadHistoryItem(**item) for item in items],
        total=len(items),
    )


@router.get("/rate-limit-status", response_model=RateLimitStatus)
def rate_limit_status(session: ActiveSessionDep) -> RateLimitStatus:
    return RateLimitStatus(
        requests_today=rate_limiter.requests_today,
        daily_limit=DATA_RATE_LIMIT_PER_DAY,
        daily_remaining=rate_limiter.daily_remaining,
    )


