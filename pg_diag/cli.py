"""Command line interface for pg_diag."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__, runtime_config
from .artifact import artifact_has_errors, report_output_paths
from .content_loader import ContentPack, iter_report_items, load_content
from .errors import PgDiagError
from .planner import build_plan
from .render.html import render_from_json
from .security import redact_error
from .snapshot import collect_snapshot
from .snapshots import collect_snapshots
from .ssh_transport import SshConfig
from .validator import has_errors, validate_content
from .versioning import select_query_variant


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PgDiagError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pg-diag")
    parser.add_argument("--version", action="version", version=f"pg-diag {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate content pack")
    _add_content_arg(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)

    list_queries_parser = subparsers.add_parser("list-queries", help="List query catalog entries")
    _add_content_arg(list_queries_parser)
    list_queries_parser.set_defaults(func=cmd_list_queries)

    list_items_parser = subparsers.add_parser("list-items", help="List report items")
    _add_content_arg(list_items_parser)
    list_items_parser.set_defaults(func=cmd_list_items)

    explain_parser = subparsers.add_parser("explain-plan", help="Build execution plan")
    _add_content_arg(explain_parser)
    _add_pg_version_arg(explain_parser)
    _add_mode_args(explain_parser)
    explain_parser.add_argument("--json", action="store_true", help="Print plan as JSON")
    explain_parser.set_defaults(func=cmd_explain_plan)

    run_query_parser = subparsers.add_parser("run-query", help="Inspect one selected query variant")
    run_query_parser.add_argument("query_id")
    _add_content_arg(run_query_parser)
    _add_pg_version_arg(run_query_parser)
    run_query_parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    run_query_parser.set_defaults(func=cmd_run_query)

    snapshot_parser = subparsers.add_parser("snapshot", help="Collect one snapshot report")
    _add_content_arg(snapshot_parser)
    _add_database_connection_args(snapshot_parser)
    _add_ssh_args(snapshot_parser)
    snapshot_parser.add_argument("--out", default="report", help="Output directory")
    _add_report_output_file_args(snapshot_parser)
    snapshot_parser.add_argument(
        "--collection-mode",
        choices=runtime_config.COLLECTION_MODES,
        default=runtime_config.DEFAULT_COLLECTION_MODE,
    )
    snapshot_parser.set_defaults(func=cmd_snapshot)

    render_parser = subparsers.add_parser("render", help="Render HTML from report JSON")
    render_parser.add_argument("--from-json", required=True, dest="from_json")
    render_parser.add_argument("--out", required=True)
    render_parser.set_defaults(func=cmd_render)

    snapshots_parser = subparsers.add_parser("snapshots", help="Collect repeated snapshots report")
    _add_content_arg(snapshots_parser)
    _add_database_connection_args(snapshots_parser)
    _add_ssh_args(snapshots_parser)
    snapshots_parser.add_argument("--out", default="report", help="Output directory")
    _add_report_output_file_args(snapshots_parser)
    snapshots_parser.add_argument(
        "--duration-seconds",
        type=float,
        default=runtime_config.SNAPSHOTS_DEFAULT_DURATION_SECONDS,
    )
    snapshots_parser.add_argument(
        "--interval-seconds",
        type=float,
        default=runtime_config.SNAPSHOTS_DEFAULT_INTERVAL_SECONDS,
    )
    snapshots_parser.add_argument(
        "--collection-mode",
        choices=runtime_config.COLLECTION_MODES,
        default=runtime_config.LOCAL_COLLECTION_MODE,
    )
    snapshots_parser.set_defaults(func=cmd_snapshots)

    return parser


def _add_content_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--content",
        default=_default_content_path(),
        help="Path to pg_diag content directory",
    )


def _default_content_path() -> str:
    working_directory_content = Path("content")
    if working_directory_content.is_dir():
        return str(working_directory_content)
    source_tree_content = Path(__file__).resolve().parents[1] / "content"
    if source_tree_content.is_dir():
        return str(source_tree_content)
    return "content"


def _add_report_output_file_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json-out", help="Exact report JSON output file")
    parser.add_argument("--html-out", help="Exact report HTML output file")


def _add_database_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dsn", help="PostgreSQL DSN")
    parser.add_argument("--host", help="PostgreSQL host; in remote mode, as seen from the SSH host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--database")
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--passfile", help="PostgreSQL password file path on the collector host")


def _add_ssh_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ssh-host", help="SSH host for full remote collection")
    parser.add_argument("--ssh-port", type=int, help="SSH port (default: 22)")
    parser.add_argument("--ssh-user")
    parser.add_argument("--ssh-key", help="SSH private key path")
    parser.add_argument(
        "--ssh-known-hosts",
        help="known_hosts file used for strict SSH host verification (default: ~/.ssh/known_hosts)",
    )
    parser.add_argument(
        "--ssh-connect-timeout",
        type=float,
        help="SSH connection timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--ssh-key-passphrase-env",
        help="Environment variable containing the private key passphrase",
    )


def _add_pg_version_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pg-version", type=int, required=True, help="PostgreSQL server_version_num")


def _add_mode_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run-mode",
        choices=[runtime_config.SNAPSHOT_MODE, runtime_config.SNAPSHOTS_MODE],
        default=runtime_config.SNAPSHOT_MODE,
    )
    parser.add_argument(
        "--collection-mode",
        choices=runtime_config.COLLECTION_MODES,
        default=runtime_config.DEFAULT_COLLECTION_MODE,
    )


def _load_and_validate(content_path: str | Path) -> tuple[ContentPack, list[Any]]:
    content = load_content(content_path)
    issues = validate_content(content)
    return content, issues


def cmd_validate(args: argparse.Namespace) -> int:
    content, issues = _load_and_validate(args.content)
    if not issues:
        print(f"OK content={content.path} checksum={content.checksum}")
        return 0
    for issue in issues:
        print(f"{issue.level.upper()} {issue.code} {issue.location}: {issue.message}")
    return 1 if has_errors(issues) else 0


def cmd_list_queries(args: argparse.Namespace) -> int:
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1
    for query_id in sorted(content.queries):
        manifest = content.queries[query_id]
        print(f"{query_id}\t{manifest.get('title', '')}")
        for variant in manifest.get("variants", []) or []:
            max_version = variant.get("max_pg_version", "+")
            print(
                f"  {variant.get('id')}\t{variant.get('min_pg_version')}-{max_version}"
                f"\t{variant.get('sql_file')}"
            )
    return 0


def cmd_list_items(args: argparse.Namespace) -> int:
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1
    for _section_id, _item_key, item_id, item in iter_report_items(content):
        source_kind = next((key for key in ("query", "script", "metric", "python") if key in item), "unknown")
        print(f"{item_id}\t{source_kind}\t{item.get(source_kind, '')}")
    return 0


def cmd_explain_plan(args: argparse.Namespace) -> int:
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1

    plan = build_plan(
        content,
        server_version_num=args.pg_version,
        mode=args.run_mode,
        collection_mode=args.collection_mode,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    else:
        _print_plan(plan.to_dict())
    return 0 if plan.supported_server_version else 1


def cmd_run_query(args: argparse.Namespace) -> int:
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1
    query = content.queries.get(args.query_id)
    if query is None:
        print(f"ERROR: unknown query id {args.query_id}", file=sys.stderr)
        return 1
    selection = select_query_variant(args.query_id, query, args.pg_version)
    if selection.status != "ok" or selection.variant is None:
        print(f"{args.query_id}\t{selection.status}\t{selection.reason}")
        return 1

    variant = selection.variant
    sql_root = (content.query_catalog.get("query_catalog") or {}).get("sql_root", "queries")
    sql_path = content.path / sql_root / variant["sql_file"]
    print(f"query_id={args.query_id}")
    print(f"variant_id={variant.get('id')}")
    print(f"sql_file={variant.get('sql_file')}")
    print(sql_path.read_text(encoding="utf-8"))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    connection_error = _connection_args_error(args, "snapshot")
    if connection_error:
        print(f"ERROR: {connection_error}", file=sys.stderr)
        return 2
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1
    connection_kwargs = {
        "host": args.host,
        "port": args.port,
        "database": args.database,
        "user": args.user,
        "password": args.password,
        "passfile": args.passfile,
    }
    ssh_config = _ssh_config(args)
    try:
        artifact = asyncio.run(
            collect_snapshot(
                content=content,
                out_dir=args.out,
                dsn=args.dsn,
                connection_kwargs=connection_kwargs,
                collection_mode=args.collection_mode,
                json_out=args.json_out,
                html_out=args.html_out,
                content_validated=True,
                ssh_config=ssh_config,
            )
        )
    except Exception as exc:
        print(f"ERROR: snapshot failed: {redact_error(exc)}", file=sys.stderr)
        return 1
    json_path, html_path = report_output_paths(args.out, args.json_out, args.html_out)
    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")
    if artifact_has_errors(artifact):
        print("ERROR: report was written with item collection errors", file=sys.stderr)
        return 1
    return 0


def cmd_snapshots(args: argparse.Namespace) -> int:
    connection_error = _connection_args_error(args, "snapshots")
    if connection_error:
        print(f"ERROR: {connection_error}", file=sys.stderr)
        return 2
    window_error = runtime_config.validate_snapshots_window(args.duration_seconds, args.interval_seconds)
    if window_error:
        print(f"ERROR: {window_error}", file=sys.stderr)
        return 2
    content, issues = _load_and_validate(args.content)
    if has_errors(issues):
        _print_validation_errors(issues)
        return 1
    connection_kwargs = {
        "host": args.host,
        "port": args.port,
        "database": args.database,
        "user": args.user,
        "password": args.password,
        "passfile": args.passfile,
    }
    ssh_config = _ssh_config(args)
    try:
        artifact = asyncio.run(
            collect_snapshots(
                content=content,
                out_dir=args.out,
                dsn=args.dsn,
                connection_kwargs=connection_kwargs,
                collection_mode=args.collection_mode,
                duration_seconds=args.duration_seconds,
                interval_seconds=args.interval_seconds,
                json_out=args.json_out,
                html_out=args.html_out,
                content_validated=True,
                ssh_config=ssh_config,
            )
        )
    except Exception as exc:
        print(f"ERROR: snapshots failed: {redact_error(exc)}", file=sys.stderr)
        return 1
    json_path, html_path = report_output_paths(args.out, args.json_out, args.html_out)
    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")
    if artifact_has_errors(artifact):
        print("ERROR: report was written with item collection errors", file=sys.stderr)
        return 1
    return 0


def _connection_args_error(args: argparse.Namespace, command: str) -> str | None:
    if not args.dsn and not (args.host and args.database and args.user):
        return f"{command} requires --dsn or --host/--database/--user"
    if args.collection_mode != runtime_config.REMOTE_COLLECTION_MODE:
        supplied = any(
            getattr(args, name, None)
            for name in (
                "ssh_host",
                "ssh_port",
                "ssh_user",
                "ssh_key",
                "ssh_known_hosts",
                "ssh_connect_timeout",
                "ssh_key_passphrase_env",
            )
        )
        if supplied:
            return "SSH options require --collection-mode remote"
        return None

    missing = [
        option
        for option, value in (
            ("--ssh-host", args.ssh_host),
            ("--ssh-user", args.ssh_user),
            ("--ssh-key", args.ssh_key),
        )
        if not value
    ]
    if missing:
        return "remote collection requires " + ", ".join(missing)
    if args.ssh_key_passphrase_env and args.ssh_key_passphrase_env not in os.environ:
        return f"environment variable {args.ssh_key_passphrase_env!r} is not set"
    try:
        config = _ssh_config(args)
        assert config is not None
        config.validate()
    except PgDiagError as exc:
        return str(exc)
    return None


def _ssh_config(args: argparse.Namespace) -> SshConfig | None:
    if args.collection_mode != runtime_config.REMOTE_COLLECTION_MODE:
        return None
    passphrase = (
        os.environ.get(args.ssh_key_passphrase_env)
        if args.ssh_key_passphrase_env
        else None
    )
    return SshConfig(
        host=str(args.ssh_host or ""),
        port=22 if args.ssh_port is None else int(args.ssh_port),
        username=str(args.ssh_user or ""),
        client_key=Path(str(args.ssh_key or "")).expanduser(),
        known_hosts=Path(
            str("~/.ssh/known_hosts" if args.ssh_known_hosts is None else args.ssh_known_hosts)
        ).expanduser(),
        connect_timeout=(
            10.0
            if args.ssh_connect_timeout is None
            else float(args.ssh_connect_timeout)
        ),
        passphrase=passphrase,
    )


def cmd_render(args: argparse.Namespace) -> int:
    try:
        render_from_json(args.from_json, args.out)
    except Exception as exc:
        print(f"ERROR: render failed: {redact_error(exc)}", file=sys.stderr)
        return 1
    print(f"Wrote {args.out}")
    return 0


def _print_validation_errors(issues: list[Any]) -> None:
    for issue in issues:
        if issue.level == "error":
            print(f"ERROR {issue.code} {issue.location}: {issue.message}", file=sys.stderr)


def _print_plan(plan: dict[str, Any]) -> None:
    print(
        f"mode={plan['mode']} collection_mode={plan['collection_mode']} "
        f"pg_version={plan['server_version_num']} supported={plan['supported_server_version']}"
    )
    if plan.get("reason"):
        print(f"reason={plan['reason']}")
    for item in plan["items"]:
        bits = [
            item["item_id"],
            item["source_kind"],
            item["status"],
            item.get("source_id") or "",
            item.get("variant_id") or "",
            item.get("collection_scope") or "",
        ]
        if item.get("reason"):
            bits.append(item["reason"])
        print("\t".join(bits))
    for job in plan.get("source_jobs") or []:
        bits = [
            job["job_id"],
            job["source_kind"],
            job["status"],
            job.get("source_id") or "",
            job.get("variant_id") or "",
            job.get("collection_scope") or "",
        ]
        if job.get("reason"):
            bits.append(job["reason"])
        print("\t".join(bits))


if __name__ == "__main__":
    raise SystemExit(main())
