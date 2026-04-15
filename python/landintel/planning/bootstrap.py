from __future__ import annotations

import argparse
from pathlib import Path

from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.storage.factory import build_storage

from .planning_register_normalize import import_borough_register_fixture
from .pld_ingest import import_pld_fixture
from .reference_layers import (
    import_baseline_pack_fixture,
    import_brownfield_fixture,
    import_constraint_fixture,
    import_flood_fixture,
    import_heritage_article4_fixture,
    import_policy_area_fixture,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Phase 3A planning fixtures.")
    parser.add_argument(
        "--dataset",
        choices=[
            "pld",
            "borough-register",
            "brownfield",
            "policy",
            "constraints",
            "flood",
            "heritage-article4",
            "baseline-pack",
            "all",
        ],
        default="all",
    )
    parser.add_argument(
        "--pld-path",
        default="tests/fixtures/planning/pld_applications.json",
    )
    parser.add_argument(
        "--borough-register-path",
        default="tests/fixtures/planning/borough_register_camden.json",
    )
    parser.add_argument(
        "--brownfield-path",
        default="tests/fixtures/planning/brownfield_sites.geojson",
    )
    parser.add_argument(
        "--policy-path",
        default="tests/fixtures/planning/policy_areas.geojson",
    )
    parser.add_argument(
        "--constraints-path",
        default="tests/fixtures/planning/constraint_features.geojson",
    )
    parser.add_argument(
        "--flood-path",
        default="tests/fixtures/planning/flood_zones.geojson",
    )
    parser.add_argument(
        "--heritage-path",
        default="tests/fixtures/planning/heritage_article4.geojson",
    )
    parser.add_argument(
        "--baseline-pack-path",
        default="tests/fixtures/planning/baseline_packs.json",
    )
    parser.add_argument("--requested-by", default="bootstrap-cli")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    session_factory = get_session_factory(settings.database_url, settings.database_echo)
    storage = build_storage(settings)

    with session_factory() as session:
        if args.dataset in {"pld", "all"}:
            result = import_pld_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.pld_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported PLD fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"borough-register", "all"}:
            result = import_borough_register_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.borough_register_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported borough-register fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"brownfield", "all"}:
            result = import_brownfield_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.brownfield_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported brownfield fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"policy", "all"}:
            result = import_policy_area_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.policy_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported policy fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"constraints", "all"}:
            result = import_constraint_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.constraints_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported constraint fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"flood", "all"}:
            result = import_flood_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.flood_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported flood fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"heritage-article4", "all"}:
            result = import_heritage_article4_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.heritage_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported heritage/article4 fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"baseline-pack", "all"}:
            result = import_baseline_pack_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.baseline_pack_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported baseline-pack fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        session.commit()


if __name__ == "__main__":
    main()
