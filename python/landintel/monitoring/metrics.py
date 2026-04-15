from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

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

