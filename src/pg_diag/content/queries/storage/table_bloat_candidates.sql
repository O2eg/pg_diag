with params as (
  select
    current_setting('block_size')::numeric as bs,
    24::numeric as page_hdr,
    8::int as ma
),
candidates_bounded as (
  select
    c.oid,
    c.relname,
    c.relkind,
    c.relpages,
    c.reltuples,
    c.reltoastrelid,
    n.nspname,
    coalesce(substring(array_to_string(c.reloptions, ' ') from 'fillfactor=([0-9]+)')::numeric, 100) as fillfactor
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'm')
    and c.relpages >= 1280
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, c.oid
  limit 501
),
coverage as (
  select (select count(*) > 500 from candidates_bounded) as candidate_sample_truncated
),
candidates as (
  select * from candidates_bounded limit 500
),
attribute_counts as (
  select
    a.attrelid,
    count(*) filter (where not a.attisdropped)::int as live_columns,
    count(*) filter (where a.attisdropped)::int as dropped_columns
  from pg_catalog.pg_attribute a
  where a.attrelid in (select oid from candidates)
    and a.attnum > 0
  group by a.attrelid
),
column_stats as (
  select
    cand.oid as relid,
    count(s.attname)::int as stats_columns,
    coalesce(sum((1 - coalesce(s.null_frac, 0)) * coalesce(s.avg_width, 0)), 0) as data_width,
    coalesce(max(coalesce(s.null_frac, 0)), 0) as max_null_frac
  from candidates cand
  left join pg_catalog.pg_stats s
    on s.schemaname = cand.nspname
    and s.tablename = cand.relname
    and not s.inherited
  group by cand.oid
),
computed as (
  select
    cand.*,
    ac.live_columns,
    ac.dropped_columns,
    cs.stats_columns,
    cs.data_width,
    p.bs,
    p.ma,
    p.page_hdr,
    (23 + case when cs.max_null_frac > 0 then (ac.live_columns + ac.dropped_columns + 7) / 8 else 0 end) as tpl_hdr_raw
  from candidates cand
  join attribute_counts ac on ac.attrelid = cand.oid
  join column_stats cs on cs.relid = cand.oid
  cross join params p
),
sized as (
  select
    *,
    (cand_hdr + ceil(data_width) + (ma - (ceil(data_width)::int % ma)) % ma)::numeric as tuple_size,
    (reltuples > 0 and data_width > 0 and stats_columns >= live_columns) as can_estimate
  from (
    select
      computed.*,
      (4 + tpl_hdr_raw + (ma - tpl_hdr_raw % ma) % ma)::numeric as cand_hdr
    from computed
  ) with_hdr
),
estimated as (
  select
    *,
    case
      when not can_estimate then null
      else ceil(
        reltuples / greatest(floor(((bs - page_hdr) * fillfactor / 100) / tuple_size), 1)
      )
    end as expected_pages
  from sized
)
select
  e.nspname as schema_name,
  e.relname as table_name,
  case e.relkind when 'r' then 'table' when 'm' then 'materialized view' else e.relkind::text end as relation_kind,
  (e.relpages::numeric * e.bs)::int8 as table_bytes,
  (coalesce(tc.relpages, 0)::numeric * e.bs)::int8 as toast_bytes,
  e.reltuples::int8 as row_estimate,
  e.fillfactor::int8 as fillfactor,
  case when e.expected_pages is null then null
    else (least(e.expected_pages, e.relpages::numeric) * e.bs)::int8 end as expected_bytes,
  case when e.expected_pages is null then null
    else (greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs)::int8 end as wasted_bytes,
  case when e.expected_pages is null then null
    else (greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages)::float8 end as bloat_percent,
  st.n_dead_tup::int8 as dead_rows,
  greatest(st.last_analyze, st.last_autoanalyze) as last_analyzed,
  e.can_estimate,
  case
    when e.reltuples <= 0 then 'No row statistics; run ANALYZE first'
    when e.data_width <= 0 or e.stats_columns < e.live_columns
      then 'Column statistics are missing for ' || (e.live_columns - e.stats_columns)::text
        || ' of ' || e.live_columns::text || ' columns; run ANALYZE or grant access to pg_stats'
    when e.dropped_columns > 0
      then 'Dropped columns still occupy space in old rows; the estimate undercounts them'
    else ''
  end as estimate_caveat,
  coverage.candidate_sample_truncated,
  case
    when not e.can_estimate then 'unknown'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 60
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 5368709120 then 'high'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 40
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 1073741824 then 'medium'
    else 'ok'
  end as risk_level,
  case
    when not e.can_estimate then 'Bloat cannot be estimated for this relation'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 60
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 5368709120
      then 'Estimated bloat exceeds 60% and 5 GiB; this is a statistical estimate - verify with pgstattuple_approx before planning VACUUM FULL, pg_repack, or CLUSTER'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 40
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 1073741824
      then 'Estimated bloat exceeds 40% and 1 GiB; this is a statistical estimate - verify before acting'
    else ''
  end as risk_reason
from estimated e
left join pg_catalog.pg_class tc on tc.oid = e.reltoastrelid
left join pg_catalog.pg_stat_user_tables st on st.relid = e.oid
cross join coverage
order by wasted_bytes desc nulls last, schema_name, table_name
