from __future__ import annotations

import argparse
from pathlib import Path

from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.geospatial.reference_data import (
    import_hmlr_title_polygons,
    import_lpa_boundaries,
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
