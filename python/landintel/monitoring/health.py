from sqlalchemy import text


def database_ready(session_factory) -> bool:
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def build_data_health_stub() -> dict[str, object]:
    return {
        "status": "stub",
        "detail": (
            "Source freshness, coverage gaps, and borough failure reporting are deferred "
            "to later phases."
        ),
    }


def build_model_health_stub() -> dict[str, object]:
    return {
        "status": "stub",
        "detail": "Model release, calibration, and drift reporting are deferred to later phases.",
    }
