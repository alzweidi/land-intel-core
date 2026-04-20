from __future__ import annotations

import argparse
from pathlib import Path

from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.geospatial.official_sources import (
    import_hmlr_title_polygons_fixture as _import_hmlr_title_polygons_fixture,
)
from landintel.geospatial.official_sources import (
    import_lpa_boundaries_fixture as _import_lpa_boundaries_fixture,
)
from landintel.storage.factory import build_storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Phase 2 reference data fixtures.")
    parser.add_argument(
        "--dataset",
        choices=["lpa", "titles", "all"],
        default="all",
        help="Which reference dataset to import.",
    )
    parser.add_argument(
        "--lpa-path",
        default="tests/fixtures/reference/london_borough_boundaries.geojson",
        help="Path to the London borough/LPA boundary fixture.",
    )
    parser.add_argument(
        "--titles-path",
        default="tests/fixtures/reference/hmlr_title_polygons.geojson",
        help="Path to the HMLR title polygon fixture.",
    )
    parser.add_argument(
        "--requested-by",
        default="bootstrap-cli",
        help="Requested-by label stored in the snapshot manifest.",
    )
    return parser


def import_lpa_boundaries(*, session, storage, fixture_path: str | Path, requested_by: str | None):
    return _import_lpa_boundaries_fixture(
        session=session,
        storage=storage,
        fixture_path=Path(fixture_path),
        requested_by=requested_by,
    )


def import_hmlr_title_polygons(
    *,
    session,
    storage,
    fixture_path: str | Path,
    requested_by: str | None,
):
    return _import_hmlr_title_polygons_fixture(
        session=session,
        storage=storage,
        fixture_path=Path(fixture_path),
        requested_by=requested_by,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    session_factory = get_session_factory(settings.database_url, settings.database_echo)
    storage = build_storage(settings)

    with session_factory() as session:
        if args.dataset in {"lpa", "all"}:
            result = import_lpa_boundaries(
                session=session,
                storage=storage,
                fixture_path=Path(args.lpa_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported LPA boundaries: "
                f"snapshot={result.source_snapshot_id} "
                f"features={result.imported_count}"
            )

        if args.dataset in {"titles", "all"}:
            result = import_hmlr_title_polygons(
                session=session,
                storage=storage,
                fixture_path=Path(args.titles_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported title polygons: "
                f"snapshot={result.source_snapshot_id} "
                f"features={result.imported_count}"
            )

        session.commit()


if __name__ == "__main__":
    main()
