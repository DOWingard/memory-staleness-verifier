"""Shared fixtures: a throwaway Python repo on disk and a terse Record builder."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from msv.types import Anchor, Record


# A small but representative repo. Keys are repo-relative paths; values are file text.
# Covers: a module-level function, a module-level class with a method, an async
# function, a file with a top-level side effect, and a file with a syntax error.
_REPO_FILES: dict[str, str] = {
    "pkg/__init__.py": "",
    "pkg/auth.py": (
        "TOKEN_TTL = 3600\n"
        "\n"
        "\n"
        "def refresh(token):\n"
        "    return token\n"
        "\n"
        "\n"
        "async def revoke(token):\n"
        "    return None\n"
        "\n"
        "\n"
        "class Session:\n"
        "    def login(self, user):\n"
        "        return user\n"
        "\n"
        "    async def logout(self):\n"
        "        return None\n"
    ),
    "pkg/parser.py": (
        "def parse(a, b, c):\n"
        "    return (a, b, c)\n"
    ),
    "pkg/broken.py": (
        "def oops(:\n"  # deliberate syntax error
        "    pass\n"
    ),
    "pkg/explode.py": (
        "import sys\n"
        "sys.exit(1)\n"  # top-level side effect; must never execute
        "\n"
        "\n"
        "def handler():\n"
        "    return 'ok'\n"
    ),
    "pkg/nameerror.py": (
        "undefined_name_at_import_time\n"  # would raise NameError if imported
        "\n"
        "\n"
        "def safe():\n"
        "    return 1\n"
    ),
}


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Materialize the sample repo under tmp_path; return the repo root Path."""
    root = tmp_path / "repo"
    for rel, text in _REPO_FILES.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return root


def snapshot_tree(root: Path) -> dict[str, tuple[float, int]]:
    """Map every file under root to (mtime_ns, size) for tamper detection."""
    snap: dict[str, tuple[float, int]] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            st = p.stat()
            snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


@pytest.fixture
def make_record():
    """Return a builder: make_record(id, *anchor_pairs, claim_text=..., commit=...).

    Each anchor_pair is (path,) or (path, symbol).
    """

    def _build(
        record_id: str,
        *anchor_pairs: tuple,
        claim_text: str = "a claim",
        commit: str | None = None,
    ) -> Record:
        anchors = tuple(
            Anchor(path=pair[0], symbol=(pair[1] if len(pair) > 1 else None))
            for pair in anchor_pairs
        )
        return Record(
            id=record_id,
            claim_text=claim_text,
            anchors=anchors,
            recorded_at_commit=commit,
        )

    return _build
