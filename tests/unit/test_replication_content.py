from __future__ import annotations

from pathlib import Path
import re

from pg_diag.content_loader import load_content
from pg_diag.planner import build_plan
from pg_diag.runtime_config import ONE_SHOT_MODE, SNAPSHOTS_MODE
from pg_diag.versioning import select_query_variant


NEW_ITEMS = (
    "synchronous_replication_status",
    "standby_recovery_state",
    "replication_capacity",
    "subscription_table_sync",
    "publication_tables_replica_identity",
)
CHART_ITEMS = (
    "replication_sender_lag_bytes",
    "replication_sender_lag_seconds",
    "standby_wal_rate",
    "standby_replay_lag_bytes",
    "standby_replay_delay",
)
VERSIONS = (100000, 110000, 120000, 130000, 140000, 150000, 160000, 170000, 180000)
VARIANTS = {
    "replication.standby_recovery_state": {
        100000: "replication_standby_recovery_state_pg10_pg11",
        110000: "replication_standby_recovery_state_pg10_pg11",
        120000: "replication_standby_recovery_state_pg12_pg13",
        130000: "replication_standby_recovery_state_pg12_pg13",
        140000: "replication_standby_recovery_state_pg14_plus",
        180000: "replication_standby_recovery_state_pg14_plus",
    },
    "replication.capacity": {
        100000: "replication_capacity_pg10_pg12",
        120000: "replication_capacity_pg10_pg12",
        130000: "replication_capacity_pg13_pg15",
        150000: "replication_capacity_pg13_pg15",
        160000: "replication_capacity_pg16",
        170000: "replication_capacity_pg17",
        180000: "replication_capacity_pg18_plus",
    },
    "replication.publication_replica_identity": {
        100000: "replication_publication_replica_identity_pg10_pg14",
        140000: "replication_publication_replica_identity_pg10_pg14",
        150000: "replication_publication_replica_identity_pg15_plus",
        180000: "replication_publication_replica_identity_pg15_plus",
    },
}


def _sql(content_path: Path, relative: str) -> str:
    return (content_path / "queries" / relative).read_text(encoding="utf-8").lower()


def test_replication_section_declares_new_items_after_subscription_workers(
    content_path: Path,
) -> None:
    content = load_content(content_path)
    items = list(content.report["sections"]["replication"]["items"])
    start = items.index("subscription_workers") + 1
    assert tuple(items[start : start + len(NEW_ITEMS)]) == NEW_ITEMS
    assert items[start + len(NEW_ITEMS)] == "recovery_prefetch"
    for key in NEW_ITEMS:
        item = content.report["sections"]["replication"]["items"][key]
        assert item["state"] == "collapsed", key
        assert "Replication" in item["tags"], key
    chart_items = list(content.report["sections"]["snapshot_charts_db"]["items"])
    assert tuple(chart_items[-len(CHART_ITEMS):]) == CHART_ITEMS
    for key in CHART_ITEMS:
        item = content.report["sections"]["snapshot_charts_db"]["items"][key]
        assert item["state"] == "collapsed", key
        assert item["metric"].startswith("replication."), key


def test_replication_query_variants_cover_postgresql_10_to_18(content_path: Path) -> None:
    content = load_content(content_path)
    for query_id, expected in VARIANTS.items():
        manifest = content.queries[query_id]
        for version, variant_id in expected.items():
            selection = select_query_variant(query_id, manifest, version)
            assert selection.status == "ok", (query_id, version)
            assert selection.variant["id"] == variant_id, (query_id, version)
    for query_id in (
        "replication.synchronous_status",
        "replication.standby_recovery_state",
        "replication.capacity",
        "replication.subscription_table_sync",
        "replication.publication_replica_identity",
        "metrics.replication_sender_lag_bytes",
        "metrics.replication_sender_lag_seconds",
        "metrics.standby_wal_rate",
        "metrics.standby_replay_lag_bytes",
        "metrics.standby_replay_delay",
    ):
        for version in VERSIONS:
            selection = select_query_variant(query_id, content.queries[query_id], version)
            assert selection.status == "ok", (query_id, version)
    legacy = select_query_variant(
        "replication.standby_recovery_state",
        content.queries["replication.standby_recovery_state"],
        110000,
    ).variant
    assert set(legacy["column_statuses"]) == {
        "primary_slot_name",
        "recovery_min_apply_delay",
        "recovery_target_timeline",
        "restore_command_configured",
    }


def test_replication_capacity_variants_track_worker_and_wal_keep_columns(
    content_path: Path,
) -> None:
    legacy = _sql(content_path, "replication/replication_capacity_pg10_pg12.sql")
    assert "wal_keep_segments" in legacy
    assert "current_setting('max_slot_wal_keep_size')" not in legacy
    assert "leader_pid" not in legacy and "worker_type" not in legacy
    pg13 = _sql(content_path, "replication/replication_capacity_pg13_pg15.sql")
    assert "wal_keep_size" in pg13 and "max_slot_wal_keep_size" in pg13
    assert "max_parallel_apply_workers_per_subscription" not in pg13
    pg16 = _sql(content_path, "replication/replication_capacity_pg16.sql")
    assert "leader_pid is not null" in pg16
    assert "max_parallel_apply_workers_per_subscription" in pg16
    assert "worker_type" not in pg16
    pg17 = _sql(content_path, "replication/replication_capacity_pg17.sql")
    assert "worker_type = 'parallel apply'" in pg17
    assert "max_active_replication_origins" not in pg17
    pg18 = _sql(content_path, "replication/replication_capacity_pg18_plus.sql")
    assert "current_setting('max_active_replication_origins')" in pg18
    for name in (
        "replication_capacity_pg10_pg12.sql",
        "replication_capacity_pg13_pg15.sql",
        "replication_capacity_pg16.sql",
        "replication_capacity_pg17.sql",
        "replication_capacity_pg18_plus.sql",
    ):
        sql = _sql(content_path, "replication/" + name)
        assert "backend_type = 'walsender'" in sql, name
        assert "from pg_catalog.pg_replication_origin_status" not in sql, name
        assert "origin_using_worker_count" in sql, name
        assert "utilization_pct" in sql, name
        assert "pg_last_wal_receive_lsn" in sql, name
        # wal_keep is informational: retained slot WAL is only compared with max_slot_wal_keep_size
        assert "when f.resource = 'wal_keep' and" not in sql, name


def test_synchronous_status_parses_first_and_any_quorums(content_path: Path) -> None:
    sql = _sql(content_path, "replication/synchronous_replication_status.sql")
    assert "(?i)^any\\s+\\d+\\s*\\(" in sql
    assert "(?i)^(?:first|any)\\s+(\\d+)" in sql
    assert "regexp_split_to_table" in sql
    assert "wait_event = 'syncrep'" in sql
    assert "quorum_satisfied" in sql
    assert "'[none]'::text" in sql
    assert "'[coverage]'::text" in sql
    assert "limit 101" in sql and "limit 1001" in sql
    assert "pg_db_role_setting" in sql and "synchronous_commit_override_count" in sql
    assert "when n.in_recovery then 'ok'" in sql
    assert "syncrep_waiting_sessions > 0 then 'high'" in sql
    assert "pg_last_wal_receive_lsn" in sql


def test_standby_recovery_state_never_exposes_the_connection_string(content_path: Path) -> None:
    for name in (
        "standby_recovery_state_pg10_pg11.sql",
        "standby_recovery_state_pg12_pg13.sql",
        "standby_recovery_state_pg14_plus.sql",
    ):
        sql = _sql(content_path, "replication/" + name)
        assert "primary_host" in sql and "primary_sslmode" in sql, name
        assert re.search(r"as\s+conninfo\b", sql) is None, name
        assert "primary_conninfo_setting as" not in sql, name
        assert "receiver_conninfo as" not in sql, name
        assert "pg_control_recovery" in sql, name
    assert "pg_get_wal_replay_pause_state" in _sql(
        content_path, "replication/standby_recovery_state_pg14_plus.sql"
    )
    assert "pg_is_wal_replay_paused" in _sql(
        content_path, "replication/standby_recovery_state_pg12_pg13.sql"
    )
    assert "current_setting('primary_conninfo'" not in _sql(
        content_path, "replication/standby_recovery_state_pg10_pg11.sql"
    )


def test_publication_replica_identity_bounds_tables_before_index_lookups(
    content_path: Path,
) -> None:
    for name in (
        "publication_replica_identity_pg10_pg14.sql",
        "publication_replica_identity_pg15_plus.sql",
    ):
        sql = _sql(content_path, "replication/" + name)
        assert "order by c.relpages desc" in sql, name
        assert sql.index("limit 10001") < sql.index("pg_index"), name
        assert "limit 20001" in sql, name
        for flag in ("candidate_sample_truncated", "membership_sample_truncated", "result_truncated"):
            assert flag in sql, (name, flag)
        assert "'[coverage]'" in sql, name
        assert "relpersistence = 'u'" in sql, name
        assert "pg_inherits" in sql and "partition_tree" in sql, name
        assert "where x.relkind = 'r'" in sql, name
    assert "pg_publication_namespace" in _sql(
        content_path, "replication/publication_replica_identity_pg15_plus.sql"
    )
    assert "pg_publication_namespace" not in _sql(
        content_path, "replication/publication_replica_identity_pg10_pg14.sql"
    )


def test_subscription_table_sync_does_not_require_superuser_catalogs(content_path: Path) -> None:
    sql = _sql(content_path, "replication/subscription_table_sync.sql")
    assert "pg_subscription_rel" in sql
    assert "pg_stat_subscription" in sql
    assert re.search(r"\bpg_catalog\.pg_subscription\b", sql) is None
    assert "limit 3001" in sql
    assert "result_truncated" in sql


def test_replication_chart_metrics_are_planned_from_dedicated_sources(content_path: Path) -> None:
    content = load_content(content_path)
    for metric_id in (
        "replication.sender_lag_bytes",
        "replication.sender_lag_seconds",
    ):
        metric = content.metrics[metric_id]
        assert metric["source_query"] == "metrics." + metric_id.split(".")[1].replace("sender", "replication_sender")
        assert metric["partition_by"] == ["dimensions.sender"]
        assert all(series["transform"] == "gauge" for series in metric["series"])
    standby_metrics = {
        "replication.standby_wal_rate": ("rate", "bytes/s"),
        "replication.standby_replay_lag_bytes": ("gauge", "bytes"),
        "replication.standby_replay_delay": ("gauge", "seconds"),
    }
    for metric_id, (transform, unit) in standby_metrics.items():
        metric = content.metrics[metric_id]
        assert metric["source_query"] == "metrics." + metric_id.split(".")[1]
        assert metric["chart"]["unit"] == unit
        assert all(series["transform"] == transform for series in metric["series"])
    for name in ("replication_sender_lag_bytes.sql", "replication_sender_lag_seconds.sql"):
        sender_sql = _sql(content_path, "metrics/" + name)
        assert "statement_timestamp() as snapshot_time" in sender_sql, name
        assert "limit 50" in sender_sql, name
    for name in ("standby_wal_rate.sql", "standby_replay_lag_bytes.sql", "standby_replay_delay.sql"):
        standby_sql = _sql(content_path, "metrics/" + name)
        assert "where pg_catalog.pg_is_in_recovery()" in standby_sql, name
    plan = build_plan(content, 180000, mode=SNAPSHOTS_MODE, collection_mode="remote-db-only")
    jobs = {job.job_id: job for job in plan.source_jobs}
    for source_id in (
        "metrics.replication_sender_lag_bytes",
        "metrics.replication_sender_lag_seconds",
        "metrics.standby_wal_rate",
        "metrics.standby_replay_lag_bytes",
        "metrics.standby_replay_delay",
    ):
        assert jobs[source_id].collection_scope == "every_snapshot", source_id
    chart_items = {
        item.item_key: item for item in plan.items if item.section_id == "snapshot_charts_db"
    }
    for key in CHART_ITEMS:
        assert chart_items[key].status == "planned", key
    one_shot = build_plan(content, 100000, mode=ONE_SHOT_MODE, collection_mode="remote-db-only")
    once_items = {item.item_key: item for item in one_shot.items if item.section_id == "replication"}
    for key in NEW_ITEMS:
        assert once_items[key].status == "planned", key


def test_truncation_never_demotes_proven_findings(content_path: Path) -> None:
    finding_queries = (
        "replication/synchronous_replication_status.sql",
        "replication/subscription_table_sync.sql",
        "replication/publication_replica_identity_pg10_pg14.sql",
        "replication/publication_replica_identity_pg15_plus.sql",
        "roles/password_validity.sql",
        "roles/effective_membership_pg10_pg15.sql",
        "roles/effective_membership_pg16_plus.sql",
        "roles/admin_option_holders_pg10_pg15.sql",
        "roles/admin_option_holders_pg16_plus.sql",
        "roles/parameter_privileges.sql",
        "roles/session_usage.sql",
        "roles/connection_security_pg10_pg11.sql",
        "roles/connection_security_pg12_plus.sql",
    )
    for relative in finding_queries:
        sql = _sql(content_path, relative)
        assert re.search(r"truncated\s+then\s+'unknown'", sql) is None, relative
        assert "'[coverage]'" in sql, relative


def test_effective_membership_carries_admin_option_on_pg16(content_path: Path) -> None:
    sql = _sql(content_path, "roles/effective_membership_pg16_plus.sql")
    assert "am.set_option or am.admin_option" in sql
    assert "am.inherit_option or am.admin_option" in sql
    assert "admin_option_in_path" in sql
    assert "pg_last_wal_receive_lsn" in _sql(content_path, "metrics/replication_sender_lag_bytes.sql")
