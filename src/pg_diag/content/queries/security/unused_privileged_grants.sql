with stats_epoch as (
  -- Lower bound of the observation window for cumulative counters: they have accumulated
  -- at least since this moment. pg_stat_database.stats_reset is exact when set (on
  -- PostgreSQL 15+ it stays NULL until pg_stat_reset() is called). A shared statistics
  -- reset after the postmaster started is either a crash recovery, which discards every
  -- counter, or a targeted pg_stat_reset_shared(), which leaves per-object counters older
  -- than it; taking the latest candidate therefore never overstates the window. Statistics
  -- survive clean restarts, so the postmaster start time is a lower bound as well.
  select
    db.stats_reset as stats_reset,
    greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset) as stats_window_start,
    case
      when db.stats_reset is not null
        and db.stats_reset = greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset)
        then 'pg_stat_database.stats_reset'
      when bg.stats_reset is not null
        and bg.stats_reset = greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset)
        then 'shared statistics reset after postmaster start (crash recovery or pg_stat_reset_shared(); per-object counters may be older)'
      else 'postmaster start time (statistics survive clean restarts, so counters may be older)'
    end as stats_window_source
  from pg_catalog.pg_stat_database db
  cross join pg_catalog.pg_stat_bgwriter bg
  where db.datname = pg_catalog.current_database()
),
storage_table_roots_bounded as (
    select c.oid, c.relname, c.relowner, c.relacl, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname !~ '^pg_(toast|temp)'
    order by c.relpages desc, n.nspname, c.relname, c.oid
    limit 10001
),
storage_table_roots as (
    select * from storage_table_roots_bounded limit 10000
),
storage_table_candidates as (
    select roots.*
    from storage_table_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
partitioned_table_roots_bounded as (
    select c.oid, c.relname, c.relowner, c.relacl, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'p'
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname !~ '^pg_(toast|temp)'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
partitioned_table_roots as (
    select * from partitioned_table_roots_bounded limit 10000
),
partitioned_table_candidates as (
    select roots.*
    from partitioned_table_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
table_candidates as (
    select * from storage_table_candidates
    union all
    select * from partitioned_table_candidates
),
expanded_acl_bounded as (
    select
        se.stats_reset,
        se.stats_window_start,
        c.nspname::text as schema_name,
        c.relname::text as table_name,
        c.oid::int8 as table_oid,
        pg_catalog.pg_get_userbyid(c.relowner)::text as table_owner,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        e.privilege_type,
        e.is_grantable,
        coalesce(s.seq_scan, 0) + coalesce(s.idx_scan, 0) as read_activity,
        coalesce(s.n_tup_ins, 0) + coalesce(s.n_tup_upd, 0) + coalesce(s.n_tup_del, 0) as write_activity
    from table_candidates c
    left join pg_stat_user_tables s on s.relid = c.oid
    cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) e
    left join pg_roles grantee on grantee.oid = e.grantee
    cross join stats_epoch se
    where e.grantee <> c.relowner
      and e.privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
      and coalesce(s.seq_scan, 0) + coalesce(s.idx_scan, 0)
          + coalesce(s.n_tup_ins, 0) + coalesce(s.n_tup_upd, 0) + coalesce(s.n_tup_del, 0) = 0
    limit 3001
),
expanded_acl as (
    select * from expanded_acl_bounded limit 3000
),
ranked_findings as (
    select *
    from expanded_acl
    order by schema_name, table_name, grantee_name, privilege_type
    limit 1001
),
coverage as (
    select
        (
            (select count(*) > 10000 from storage_table_roots_bounded)
            or (select count(*) > 10000 from partitioned_table_roots_bounded)
        ) as candidate_sample_truncated,
        (select count(*) > 3000 from expanded_acl_bounded) as acl_expansion_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select * from ranked_findings limit 1000
)
select
    findings.stats_reset,
    findings.stats_window_start,
    findings.schema_name,
    findings.table_name,
    findings.table_oid,
    findings.table_owner,
    findings.grantee_name,
    findings.privilege_type,
    findings.is_grantable,
    findings.read_activity,
    findings.write_activity,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown' as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
            then 'Unused-grant finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'No table activity is visible since the statistics window start; this does not prove that the privilege is unused'
    end as risk_reason
from findings
cross join coverage
union all
select
    null::timestamptz,
    null::timestamptz,
    '[coverage]'::text,
    ''::text,
    null::int8,
    ''::text,
    ''::text,
    ''::text,
    false,
    0::int8,
    0::int8,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded table candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by schema_name, table_name, grantee_name, privilege_type
