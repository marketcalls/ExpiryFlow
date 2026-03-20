import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta

import duckdb

from config import DATA_RATE_LIMIT_PER_DAY, DATA_RATE_LIMIT_PER_SECOND
from services.dhan_data_service import build_strike_label, fetch_rolling_option

logger = logging.getLogger(__name__)

MAX_DAYS_PER_CALL = 30


class DataApiRateLimiter:
    def __init__(self, max_per_second: int = DATA_RATE_LIMIT_PER_SECOND, max_per_day: int = DATA_RATE_LIMIT_PER_DAY):
        self._max_per_second = max_per_second
        self._max_per_day = max_per_day
        self._second_timestamps: list[float] = []
        self._day_count = 0
        self._day_start = time.time()
        self._lock = threading.Lock()

    def wait_if_needed(self):
        with self._lock:
            now = time.time()
            if now - self._day_start >= 86400:
                self._day_count = 0
                self._day_start = now
            if self._day_count >= self._max_per_day:
                raise RuntimeError("Daily API limit reached (100,000 requests)")
            self._second_timestamps = [t for t in self._second_timestamps if now - t < 1.0]
            if len(self._second_timestamps) >= self._max_per_second:
                sleep_time = 1.0 - (now - self._second_timestamps[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self._second_timestamps.append(time.time())
            self._day_count += 1

    @property
    def daily_remaining(self) -> int:
        return max(0, self._max_per_day - self._day_count)

    @property
    def requests_today(self) -> int:
        return self._day_count


rate_limiter = DataApiRateLimiter()

_jobs: dict[str, dict] = {}
_cancel_flags: dict[str, bool] = {}


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total_requests": 0,
        "completed_requests": 0,
        "skipped_requests": 0,
        "failed_requests": 0,
        "rows_downloaded": 0,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
    }
    _cancel_flags[job_id] = False
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def cancel_job(job_id: str):
    _cancel_flags[job_id] = True


def get_active_jobs() -> list[dict]:
    return [j for j in _jobs.values() if j["status"] in ("pending", "running")]


def _chunk_date_range(from_date: date, to_date: date) -> list[tuple[date, date]]:
    """Split a date range into chunks of MAX_DAYS_PER_CALL days."""
    chunks = []
    cursor = from_date
    while cursor <= to_date:
        chunk_end = min(cursor + timedelta(days=MAX_DAYS_PER_CALL), to_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _has_data(
    duck: duckdb.DuckDBPyConnection,
    underlying_scrip: str,
    expiry_flag: str,
    expiry_code: int,
    interval: str,
    strike_label: str,
    option_type: str,
    chunk_from: date,
    chunk_to: date,
) -> bool:
    """Check if this chunk was already downloaded by looking at download_metadata.

    Returns True only if a previous download fully covers [chunk_from, chunk_to].
    """
    row = duck.execute(
        """
        SELECT COUNT(*) FROM download_metadata
        WHERE underlying_scrip = ?
          AND expiry_flag = ?
          AND expiry_code = ?
          AND interval = ?
          AND strike_label = ?
          AND option_type = ?
          AND from_date <= ?
          AND to_date >= ?
        """,
        [
            underlying_scrip, expiry_flag, expiry_code, interval,
            strike_label, option_type,
            chunk_from.isoformat(), chunk_to.isoformat(),
        ],
    ).fetchone()
    return row is not None and row[0] > 0


def _insert_ohlcv(
    duck: duckdb.DuckDBPyConnection,
    underlying_scrip: str,
    exchange_segment: str,
    instrument: str,
    expiry_flag: str,
    expiry_code: int,
    interval: str,
    strike_label: str,
    option_type: str,
    bars: list[dict],
):
    if not bars:
        return
    for bar in bars:
        duck.execute(
            """
            INSERT OR REPLACE INTO expired_options_ohlcv
            (underlying_scrip, exchange_segment, instrument,
             expiry_flag, expiry_code, interval, strike_label, strike_price,
             option_type, timestamp, open, high, low, close,
             volume, oi, iv, spot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                underlying_scrip, exchange_segment, instrument,
                expiry_flag, expiry_code, interval, strike_label,
                bar.get("strike_price"),
                option_type, bar["timestamp"],
                bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close"),
                bar.get("volume"), bar.get("oi"),
                bar.get("iv"), bar.get("spot"),
            ],
        )


def _record_metadata(
    duck: duckdb.DuckDBPyConnection,
    underlying_scrip: str,
    exchange_segment: str,
    instrument: str,
    expiry_flag: str,
    expiry_code: int,
    interval: str,
    strike_label: str,
    option_type: str,
    from_date: str,
    to_date: str,
    row_count: int,
):
    duck.execute(
        """
        INSERT INTO download_metadata
        (id, underlying_scrip, exchange_segment, instrument,
         expiry_flag, expiry_code, interval, strike_label,
         option_type, from_date, to_date, row_count, downloaded_at)
        VALUES (nextval('download_metadata_id_seq'), ?, ?, ?,
                ?, ?, ?, ?, ?, ?::DATE, ?::DATE, ?, CURRENT_TIMESTAMP)
        """,
        [
            underlying_scrip, exchange_segment, instrument,
            expiry_flag, expiry_code, interval, strike_label,
            option_type, from_date, to_date, row_count,
        ],
    )


def run_download_job(
    job_id: str,
    underlying_scrip: str,
    exchange_segment: str,
    instrument: str,
    security_id: int,
    option_types: list[str],
    expiry_flags: list[str],
    expiry_codes: list[int],
    strike_range: int,
    interval: str,
    from_date_str: str,
    to_date_str: str,
    access_token: str,
    client_id: str,
    duckdb_path: str,
):
    duck = duckdb.connect(duckdb_path)
    job = _jobs[job_id]
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()

    try:
        from_d = date.fromisoformat(from_date_str)
        to_d = date.fromisoformat(to_date_str)

        # Chunk dates into 30-day windows (API limit)
        date_chunks = _chunk_date_range(from_d, to_d)

        # Build strike offsets: -N ... -1, ATM, +1 ... +N
        strike_offsets = list(range(-strike_range, strike_range + 1))

        # Map CALL/PUT for API
        api_option_map = {"CE": "CALL", "PE": "PUT", "CALL": "CALL", "PUT": "PUT"}

        # Build work items: (expiry_flag, expiry_code, strike_label, api_option_type, storage_ot, chunk_from, chunk_to)
        all_work = []
        for ef in expiry_flags:
            for ec in expiry_codes:
                for offset in strike_offsets:
                    strike_label = build_strike_label(offset)
                    for ot in option_types:
                        api_ot = api_option_map.get(ot, ot)
                        for chunk_from, chunk_to in date_chunks:
                            all_work.append((ef, ec, strike_label, api_ot, ot, chunk_from, chunk_to))

        job["total_requests"] = len(all_work)
        logger.info("Job %s: %d work items, %d date chunks, %d strikes, %d option types, expiry_flags=%s, expiry_codes=%s",
                     job_id, len(all_work), len(date_chunks), len(strike_offsets), len(option_types), expiry_flags, expiry_codes)

        for expiry_flag, expiry_code, strike_label, api_ot, storage_ot, chunk_from, chunk_to in all_work:
            if _cancel_flags.get(job_id, False):
                job["status"] = "cancelled"
                job["completed_at"] = datetime.now().isoformat()
                return

            try:
                # Skip API call if data already exists for this chunk
                if _has_data(duck, underlying_scrip, expiry_flag, expiry_code, interval, strike_label, storage_ot, chunk_from, chunk_to):
                    logger.info("Skipping %s %s/%s %s %s [%s-%s] — data exists", underlying_scrip, expiry_flag, expiry_code, strike_label, storage_ot, chunk_from, chunk_to)
                    job["skipped_requests"] += 1
                    job["completed_requests"] += 1
                    continue

                rate_limiter.wait_if_needed()
                result = fetch_rolling_option(
                    access_token=access_token,
                    client_id=client_id,
                    exchange_segment=exchange_segment,
                    security_id=security_id,
                    instrument=instrument,
                    expiry_flag=expiry_flag,
                    expiry_code=expiry_code,
                    strike=strike_label,
                    drv_option_type=api_ot,
                    interval=interval,
                    from_date=chunk_from.isoformat(),
                    to_date=chunk_to.isoformat(),
                )
                for ot_key, bars in result.items():
                    _insert_ohlcv(duck, underlying_scrip, exchange_segment, instrument, expiry_flag, expiry_code, interval, strike_label, ot_key, bars)
                    _record_metadata(duck, underlying_scrip, exchange_segment, instrument, expiry_flag, expiry_code, interval, strike_label, ot_key, chunk_from.isoformat(), chunk_to.isoformat(), len(bars))
                    job["rows_downloaded"] += len(bars)
                job["completed_requests"] += 1
            except RuntimeError as e:
                job["error_message"] = str(e)
                job["status"] = "failed"
                job["completed_at"] = datetime.now().isoformat()
                return
            except Exception as e:
                logger.error("Download error for %s %s/%s strike=%s %s [%s-%s]: %s", underlying_scrip, expiry_flag, expiry_code, strike_label, api_ot, chunk_from, chunk_to, str(e))
                job["failed_requests"] += 1
                job["completed_requests"] += 1

        job["status"] = "completed"
        job["completed_at"] = datetime.now().isoformat()
    except Exception as e:
        logger.error("Download job failed: %s", str(e), exc_info=True)
        job["status"] = "failed"
        job["error_message"] = str(e)
        job["completed_at"] = datetime.now().isoformat()
    finally:
        duck.close()


def start_download_thread(
    job_id: str,
    underlying_scrip: str,
    exchange_segment: str,
    instrument: str,
    security_id: int,
    option_types: list[str],
    expiry_flags: list[str],
    expiry_codes: list[int],
    strike_range: int,
    interval: str,
    from_date: str,
    to_date: str,
    access_token: str,
    client_id: str,
    duckdb_path: str,
):
    thread = threading.Thread(
        target=run_download_job,
        args=(
            job_id, underlying_scrip, exchange_segment, instrument,
            security_id, option_types, expiry_flags, expiry_codes,
            strike_range, interval, from_date, to_date,
            access_token, client_id, duckdb_path,
        ),
        daemon=True,
    )
    thread.start()


def get_download_history(duck: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = duck.execute(
        """
        SELECT underlying_scrip, expiry_flag, expiry_code, interval, strike_label,
               option_type, from_date, to_date, row_count, downloaded_at
        FROM download_metadata
        ORDER BY downloaded_at DESC
        LIMIT 100
        """
    ).fetchall()
    return [
        {
            "underlying_scrip": r[0],
            "expiry_flag": r[1],
            "expiry_code": r[2],
            "interval": r[3],
            "strike_label": r[4],
            "option_type": r[5],
            "from_date": str(r[6]),
            "to_date": str(r[7]),
            "row_count": r[8],
            "downloaded_at": str(r[9]),
        }
        for r in rows
    ]
