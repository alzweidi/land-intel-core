from __future__ import annotations

import argparse
from pathlib import Path

from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.storage.factory import build_storage
from landintel.valuation.assumptions import ensure_default_assumption_set
from landintel.valuation.market import import_land_comp_fixture

from .official_sources import import_hmlr_price_paid_fixture, import_ukhpi_fixture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Phase 7A valuation fixtures.")
    parser.add_argument(
        "--dataset",
        choices=["hmlr-price-paid", "ukhpi", "land-comps", "assumptions", "all"],
        default="all",
    )
    parser.add_argument(
        "--hmlr-price-paid-path",
        default="tests/fixtures/valuation/hmlr_price_paid_london.json",
    )
    parser.add_argument(
        "--ukhpi-path",
        default="tests/fixtures/valuation/ukhpi_london.json",
    )
    parser.add_argument(
        "--land-comps-path",
        default="tests/fixtures/valuation/land_comps_london.json",
    )
    parser.add_argument("--requested-by", default="bootstrap-cli")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    session_factory = get_session_factory(settings.database_url, settings.database_echo)
    storage = build_storage(settings)

    with session_factory() as session:
        if args.dataset in {"assumptions", "all"}:
            assumption_set = ensure_default_assumption_set(session)
            print(
                "Seeded valuation assumptions: "
                f"version={assumption_set.version} id={assumption_set.id}"
            )

        if args.dataset in {"hmlr-price-paid", "all"}:
            result = import_hmlr_price_paid_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.hmlr_price_paid_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported HMLR Price Paid fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"ukhpi", "all"}:
            result = import_ukhpi_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.ukhpi_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported UKHPI fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        if args.dataset in {"land-comps", "all"}:
            result = import_land_comp_fixture(
                session=session,
                storage=storage,
                fixture_path=Path(args.land_comps_path),
                requested_by=args.requested_by,
            )
            print(
                "Imported land comps fixture: "
                f"snapshot={result.source_snapshot_id} "
                f"records={result.imported_count} "
                f"coverage={result.coverage_count}"
            )

        session.commit()


if __name__ == "__main__":
    main()
