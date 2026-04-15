from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

REQUEST_COUNT = Counter(
    "landintel_http_requests_total",
    "HTTP requests processed by the API.",
    ["method", "path", "status_code"],
)
JOB_STATUS_TOTAL = Counter(
    "landintel_job_status_total",
    "Job status transitions.",
    ["job_type", "status"],
)
JOB_CLAIMS_TOTAL = Counter(
    "landintel_job_claim_total",
    "Jobs claimed by a worker.",
    ["worker_id", "job_type"],
)
WORKER_LOOP_COUNT = Counter(
    "landintel_worker_loop_total",
    "Worker loop iterations.",
)
UPLIFT_NULL_RATE = Gauge(
    "landintel_uplift_null_rate",
    "Share of valuation results with null uplift.",
)
ASKING_PRICE_MISSING_RATE = Gauge(
    "landintel_asking_price_missing_rate",
    "Share of valuation results missing an asking price basis.",
)
VALUATION_QUALITY_TOTAL = Gauge(
    "landintel_valuation_quality_total",
    "Count of valuation results by quality bucket.",
    ["quality"],
)


def register_fastapi_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        response = await call_next(request)
        REQUEST_COUNT.labels(
            method=request.method,
            path=request.url.path,
            status_code=str(response.status_code),
        ).inc()
        return response


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def update_valuation_metrics(metrics: dict[str, object]) -> None:
    uplift_null_rate = metrics.get("uplift_null_rate")
    if isinstance(uplift_null_rate, (int, float)):
        UPLIFT_NULL_RATE.set(float(uplift_null_rate))
    asking_price_missing_rate = metrics.get("asking_price_missing_rate")
    if isinstance(asking_price_missing_rate, (int, float)):
        ASKING_PRICE_MISSING_RATE.set(float(asking_price_missing_rate))
    quality_distribution = metrics.get("valuation_quality_distribution")
    if isinstance(quality_distribution, dict):
        for quality, count in quality_distribution.items():
            if isinstance(count, (int, float)):
                VALUATION_QUALITY_TOTAL.labels(quality=str(quality)).set(float(count))
