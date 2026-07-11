"""Local and SSH-backed access to database-host operating system facts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import stat
from typing import Any

from . import runtime_config
from .local_process import run_local_process
from .ssh_transport import SshCommandResult, SshTransport


DEFAULT_FILE_LIMIT = 4 * 1024 * 1024


@dataclass(frozen=True)
class HostStat:
    path: str
    mode: int
    uid: int | None
    gid: int | None
    owner: str
    group: str
    size: int
    mtime: float

    @property
    def is_file(self) -> bool:
        return stat.S_ISREG(self.mode)

    @property
    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.mode)

    @property
    def is_symlink(self) -> bool:
        return stat.S_ISLNK(self.mode)


@dataclass(frozen=True)
class HostDirEntry:
    path: str
    name: str
    stat: HostStat


class HostAccess:
    """Asynchronous host operations used by trusted item evaluators."""

    async def stat(self, path: str | Path, *, follow_symlinks: bool = True) -> HostStat:
        raise NotImplementedError

    async def read_bytes(self, path: str | Path, *, limit: int = DEFAULT_FILE_LIMIT) -> bytes:
        raise NotImplementedError

    async def read_text(self, path: str | Path, *, limit: int = DEFAULT_FILE_LIMIT) -> str:
        return (await self.read_bytes(path, limit=limit)).decode("utf-8", errors="replace")

    async def list_dir(self, path: str | Path) -> list[HostDirEntry]:
        raise NotImplementedError

    async def glob(self, pattern: str | Path) -> list[str]:
        raise NotImplementedError

    async def realpath(self, path: str | Path) -> str:
        raise NotImplementedError

    async def readlink(self, path: str | Path) -> str:
        raise NotImplementedError

    async def environ(self) -> dict[str, str]:
        raise NotImplementedError

    async def run(
        self,
        arguments: tuple[str, ...],
        *,
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        raise NotImplementedError

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        raise NotImplementedError

    async def exists(self, path: str | Path) -> bool:
        try:
            await self.stat(path)
            return True
        except (FileNotFoundError, PermissionError, OSError):
            return False

    async def is_file(self, path: str | Path) -> bool:
        try:
            return (await self.stat(path)).is_file
        except (FileNotFoundError, PermissionError, OSError):
            return False

    async def is_dir(self, path: str | Path) -> bool:
        try:
            return (await self.stat(path)).is_dir
        except (FileNotFoundError, PermissionError, OSError):
            return False


class LocalHostAccess(HostAccess):
    async def stat(self, path: str | Path, *, follow_symlinks: bool = True) -> HostStat:
        def inspect() -> HostStat:
            value = Path(path)
            result = value.stat() if follow_symlinks else value.lstat()
            return HostStat(
                path=str(value),
                mode=result.st_mode,
                uid=result.st_uid,
                gid=result.st_gid,
                owner=_local_uid_name(result.st_uid),
                group=_local_gid_name(result.st_gid),
                size=result.st_size,
                mtime=result.st_mtime,
            )

        return await asyncio.to_thread(inspect)

    async def read_bytes(self, path: str | Path, *, limit: int = DEFAULT_FILE_LIMIT) -> bytes:
        def read() -> bytes:
            with Path(path).open("rb") as stream:
                value = stream.read(limit + 1)
            if len(value) > limit:
                raise OSError(f"host file exceeds the {limit}-byte read limit: {path}")
            return value

        return await asyncio.to_thread(read)

    async def list_dir(self, path: str | Path) -> list[HostDirEntry]:
        def scan() -> list[HostDirEntry]:
            rows: list[HostDirEntry] = []
            for child in Path(path).iterdir():
                result = child.lstat()
                rows.append(
                    HostDirEntry(
                        path=str(child),
                        name=child.name,
                        stat=HostStat(
                            path=str(child),
                            mode=result.st_mode,
                            uid=result.st_uid,
                            gid=result.st_gid,
                            owner=_local_uid_name(result.st_uid),
                            group=_local_gid_name(result.st_gid),
                            size=result.st_size,
                            mtime=result.st_mtime,
                        ),
                    )
                )
            return sorted(rows, key=lambda row: row.name)

        return await asyncio.to_thread(scan)

    async def glob(self, pattern: str | Path) -> list[str]:
        import glob

        return await asyncio.to_thread(lambda: sorted(glob.glob(str(pattern))))

    async def realpath(self, path: str | Path) -> str:
        return await asyncio.to_thread(lambda: str(Path(path).resolve()))

    async def readlink(self, path: str | Path) -> str:
        return await asyncio.to_thread(os.readlink, path)

    async def environ(self) -> dict[str, str]:
        return dict(os.environ)

    async def run(
        self,
        arguments: tuple[str, ...],
        *,
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        def execute() -> SshCommandResult:
            completed = run_local_process(
                arguments,
                timeout=timeout,
                env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            )
            return SshCommandResult(completed.returncode, completed.stdout, completed.stderr)

        return await asyncio.to_thread(execute)

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        def execute() -> SshCommandResult:
            completed = run_local_process(
                ("/bin/sh", "-s", "--", *arguments),
                input_data=script,
                timeout=timeout,
                env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            )
            return SshCommandResult(completed.returncode, completed.stdout, completed.stderr)

        return await asyncio.to_thread(execute)


class SshHostAccess(HostAccess):
    def __init__(self, transport: SshTransport) -> None:
        self.transport = transport
        self._identity_lock = asyncio.Lock()
        self._uid_names: dict[int, str] = {}
        self._gid_names: dict[int, str] = {}

    async def stat(self, path: str | Path, *, follow_symlinks: bool = True) -> HostStat:
        value = str(path)
        sftp = await self.transport.sftp()
        try:
            attrs = await sftp.stat(value, follow_symlinks=follow_symlinks)
        except Exception as exc:
            raise _mapped_sftp_error(exc, value) from exc
        permissions = attrs.permissions
        if permissions is None:
            raise OSError(f"SFTP server returned no permissions for {value}")
        uid = int(attrs.uid) if attrs.uid is not None else None
        gid = int(attrs.gid) if attrs.gid is not None else None
        owner, group = await asyncio.gather(
            self._identity_name("passwd", attrs.owner, uid),
            self._identity_name("group", attrs.group, gid),
        )
        return HostStat(
            path=value,
            mode=int(permissions),
            uid=uid,
            gid=gid,
            owner=owner,
            group=group,
            size=int(attrs.size or 0),
            mtime=float(attrs.mtime or 0),
        )

    async def read_bytes(self, path: str | Path, *, limit: int = DEFAULT_FILE_LIMIT) -> bytes:
        value = str(path)
        sftp = await self.transport.sftp()
        try:
            async with sftp.open(value, "rb") as stream:
                data = await stream.read(limit + 1)
        except Exception as exc:
            raise _mapped_sftp_error(exc, value) from exc
        result = bytes(data)
        if len(result) > limit:
            raise OSError(f"host file exceeds the {limit}-byte read limit: {value}")
        return result

    async def list_dir(self, path: str | Path) -> list[HostDirEntry]:
        value = str(path)
        sftp = await self.transport.sftp()
        rows: list[HostDirEntry] = []
        try:
            async for entry in sftp.scandir(value):
                name = str(entry.filename)
                if name in {".", ".."}:
                    continue
                child = str(Path(value) / name)
                attrs = entry.attrs
                permissions = attrs.permissions
                if permissions is None:
                    attrs = await sftp.lstat(child)
                    permissions = attrs.permissions
                if permissions is None:
                    continue
                uid = int(attrs.uid) if attrs.uid is not None else None
                gid = int(attrs.gid) if attrs.gid is not None else None
                owner, group = await asyncio.gather(
                    self._identity_name("passwd", attrs.owner, uid),
                    self._identity_name("group", attrs.group, gid),
                )
                rows.append(
                    HostDirEntry(
                        path=child,
                        name=name,
                        stat=HostStat(
                            path=child,
                            mode=int(permissions),
                            uid=uid,
                            gid=gid,
                            owner=owner,
                            group=group,
                            size=int(attrs.size or 0),
                            mtime=float(attrs.mtime or 0),
                        ),
                    )
                )
        except Exception as exc:
            raise _mapped_sftp_error(exc, value) from exc
        return sorted(rows, key=lambda row: row.name)

    async def glob(self, pattern: str | Path) -> list[str]:
        value = str(pattern)
        sftp = await self.transport.sftp()
        try:
            return sorted(str(path) for path in await sftp.glob(value, error_handler=False))
        except Exception as exc:
            mapped = _mapped_sftp_error(exc, value)
            if isinstance(mapped, FileNotFoundError):
                return []
            raise mapped from exc

    async def realpath(self, path: str | Path) -> str:
        value = str(path)
        sftp = await self.transport.sftp()
        try:
            return str(await sftp.realpath(value))
        except Exception as exc:
            raise _mapped_sftp_error(exc, value) from exc

    async def readlink(self, path: str | Path) -> str:
        value = str(path)
        sftp = await self.transport.sftp()
        try:
            return str(await sftp.readlink(value))
        except Exception as exc:
            raise _mapped_sftp_error(exc, value) from exc

    async def environ(self) -> dict[str, str]:
        result = await self.transport.run_bytes(
            "LC_ALL=C LANG=C exec env -0",
            timeout=runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return {}
        values: dict[str, str] = {}
        for entry in bytes(result.stdout).split(b"\0"):
            if b"=" not in entry:
                continue
            key, value = entry.split(b"=", 1)
            values[key.decode("utf-8", errors="replace")] = value.decode(
                "utf-8", errors="replace"
            )
        return values

    async def run(
        self,
        arguments: tuple[str, ...],
        *,
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        command = " ".join(shlex.quote(argument) for argument in arguments)
        return await self.transport.run(
            f"LC_ALL=C LANG=C exec {command}",
            timeout=timeout,
        )

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
        timeout: float = runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> SshCommandResult:
        return await self.transport.run_script(
            script,
            arguments=arguments,
            timeout=timeout,
        )

    async def _identity_name(
        self,
        database: str,
        supplied_name: Any,
        numeric_id: int | None,
    ) -> str:
        direct = _sftp_name(supplied_name, None)
        if direct and not direct.isdigit():
            return direct
        if numeric_id is None and direct.isdigit():
            numeric_id = int(direct)
        if numeric_id is None:
            return ""
        cache = self._uid_names if database == "passwd" else self._gid_names
        if numeric_id in cache:
            return cache[numeric_id]
        async with self._identity_lock:
            if numeric_id in cache:
                return cache[numeric_id]
            result = await self.transport.run(
                f"LC_ALL=C LANG=C exec getent {database} {numeric_id}",
                timeout=runtime_config.HOST_COMMAND_TIMEOUT_SECONDS,
            )
            fields = result.stdout.splitlines()[0].split(":") if result.stdout.splitlines() else []
            cache[numeric_id] = fields[0] if len(fields) >= 3 else str(numeric_id)
            return cache[numeric_id]


def _mapped_sftp_error(exc: Exception, path: str) -> OSError:
    name = type(exc).__name__.lower()
    if "nosuchfile" in name or "notfound" in name:
        return FileNotFoundError(path)
    if "permissiondenied" in name:
        return PermissionError(path)
    return OSError(f"SFTP operation failed for {path}: {exc}")


def _sftp_name(value: Any, numeric: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value not in (None, ""):
        return str(value)
    return "" if numeric is None else str(numeric)


def _local_uid_name(uid: int) -> str:
    try:
        import pwd

        return pwd.getpwuid(uid).pw_name
    except (ImportError, KeyError):
        return str(uid)


def _local_gid_name(gid: int) -> str:
    try:
        import grp

        return grp.getgrgid(gid).gr_name
    except (ImportError, KeyError):
        return str(gid)
