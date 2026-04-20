from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path


def _extract_function(repo_root: Path, name: str) -> str:
    smoke_script = (repo_root / "scripts" / "smoke_prod.sh").read_text()
    match = re.search(
        rf"{name}\(\) \{{\n(?P<body>.*?)^\}}",
        smoke_script,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{name}() was not found in scripts/smoke_prod.sh")
    return f"{name}() {{\n" + match.group("body") + "\n}"


def test_smoke_prod_count_collection_items_reads_json_from_curl_output(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    curl_cmd_function = _extract_function(repo_root, "curl_cmd")
    count_function = _extract_function(repo_root, "count_collection_items")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"printf '%s\\n' \"$@\" > {curl_log}\n"
        "printf '%s' '{\"items\":[{\"id\":1},{\"id\":2},{\"id\":3}]}'\n"
    )
    fake_curl.chmod(0o755)

    bash_script = textwrap.dedent(
        f"""\
        set -euo pipefail
        APP_ORIGIN="https://app.example.test"
        app_origin_curl=()
        {curl_cmd_function}
        {count_function}
        count_collection_items "https://api.example.test/items" --cookie "session=abc"
        """
    )
    result = subprocess.run(
        ["/bin/bash", "-c", bash_script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy() | {"CURL_BIN": str(fake_curl)},
    )

    assert result.stdout.strip() == "3"
    assert curl_log.read_text().splitlines() == [
        "--fail",
        "--silent",
        "--show-error",
        "--cookie",
        "session=abc",
        "https://api.example.test/items",
    ]


def test_smoke_prod_count_collection_items_counts_top_level_list(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    curl_cmd_function = _extract_function(repo_root, "curl_cmd")
    count_function = _extract_function(repo_root, "count_collection_items")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s' '[{\"id\":1},{\"id\":2}]'\n"
    )
    fake_curl.chmod(0o755)

    bash_script = textwrap.dedent(
        f"""\
        set -euo pipefail
        APP_ORIGIN="https://app.example.test"
        app_origin_curl=()
        {curl_cmd_function}
        {count_function}
        count_collection_items "https://api.example.test/list"
        """
    )
    result = subprocess.run(
        ["/bin/bash", "-c", bash_script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy() | {"CURL_BIN": str(fake_curl)},
    )

    assert result.stdout.strip() == "2"
