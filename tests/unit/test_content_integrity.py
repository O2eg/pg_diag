from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from pg_diag._content_state import _rebase
from pg_diag.content_loader import load_content
from pg_diag.errors import ContentIntegrityError


def _copy_content(content_path: Path, tmp_path: Path) -> Path:
    copied = tmp_path / "content"
    shutil.copytree(content_path, copied)
    return copied


def test_modified_content_member_is_rejected(content_path: Path, tmp_path: Path) -> None:
    copied = _copy_content(content_path, tmp_path)
    report = copied / "report.yaml"
    report.write_text(report.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    with pytest.raises(ContentIntegrityError):
        load_content(copied)


def test_added_content_member_is_rejected(content_path: Path, tmp_path: Path) -> None:
    copied = _copy_content(content_path, tmp_path)
    (copied / "queries" / "injected.sql").write_text("select 1;\n", encoding="utf-8")

    with pytest.raises(ContentIntegrityError):
        load_content(copied)


def test_removed_content_member_is_rejected(content_path: Path, tmp_path: Path) -> None:
    copied = _copy_content(content_path, tmp_path)
    next((copied / "scripts").rglob("*.sh")).unlink()

    with pytest.raises(ContentIntegrityError):
        load_content(copied)


def test_untracked_file_type_does_not_change_baseline(content_path: Path, tmp_path: Path) -> None:
    copied = _copy_content(content_path, tmp_path)
    (copied / "collector-note.bin").write_bytes(b"not executable content")

    assert load_content(copied).path == copied.resolve()


@pytest.mark.parametrize(
    "name",
    ["README.md", "EXTENDING.md", "ITEM_DEVELOPMENT_SPEC.md"],
)
def test_content_documentation_does_not_change_baseline(
    content_path: Path,
    tmp_path: Path,
    name: str,
) -> None:
    copied = _copy_content(content_path, tmp_path)
    document = copied / name
    document.write_text(
        document.read_text(encoding="utf-8") + "\n<!-- reviewed -->\n",
        encoding="utf-8",
    )

    assert load_content(copied).path == copied.resolve()


def test_internal_rebase_accepts_deliberate_content_update(
    content_path: Path,
    tmp_path: Path,
) -> None:
    copied = _copy_content(content_path, tmp_path)
    report = copied / "report.yaml"
    report.write_text(report.read_text(encoding="utf-8") + "\n# reviewed\n", encoding="utf-8")

    with pytest.raises(ContentIntegrityError):
        load_content(copied)

    index = _rebase(copied)

    assert index == copied / "integrity.sha256"
    assert index.stat().st_mode & 0o777 == 0o600
    assert load_content(copied).path == copied.resolve()
