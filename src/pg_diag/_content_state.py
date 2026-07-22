"""Internal content admission state."""

from __future__ import annotations

from contextvars import ContextVar
from hashlib import sha256
import hmac
import os
from pathlib import Path
import re
import tempfile


_TYPES = frozenset({".py", ".sh", ".sql", ".yaml", ".yml"})
_INDEX = "integrity.sha256"
_LINE = re.compile(r"sha256:[0-9a-f]{64}")
_SLOT: ContextVar[tuple[Path, bytes] | None] = ContextVar("content_slot", default=None)


def _members(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in _TYPES:
            continue
        if path.is_symlink():
            raise OSError("linked content member")
        if not path.is_file():
            continue
        resolved = path.resolve()
        resolved.relative_to(root)
        paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def _fold(root: Path) -> str:
    digest = sha256()
    for path in _members(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _reference(root: Path) -> str:
    path = root / _INDEX
    if path.is_symlink() or not path.is_file():
        raise OSError("content index is not a regular file")
    value = path.read_text(encoding="ascii").strip()
    if _LINE.fullmatch(value) is None:
        raise ValueError("invalid content index")
    return value


def _seed(root: Path) -> str | None:
    root = root.resolve()
    token = b""
    revision: str | None = None
    try:
        expected = _reference(root)
        actual = _fold(root)
        if hmac.compare_digest(expected, actual):
            token = sha256(os.fsencode(root) + b"\0" + actual.encode("ascii")).digest()
            revision = actual
    except (OSError, UnicodeError, ValueError):
        pass
    _SLOT.set((root, token))
    return revision


def _allows(path: Path) -> bool:
    state = _SLOT.get()
    if state is None:
        return True
    root, token = state
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return True
    return bool(token)


def _rebase(root: str | Path) -> Path:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise OSError(f"content root is not a directory: {root_path}")
    value = _fold(root_path)
    target = root_path / _INDEX
    if target.is_symlink():
        raise OSError("content index must not be a symbolic link")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            dir=root_path,
            prefix=".content-",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, target)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return target
