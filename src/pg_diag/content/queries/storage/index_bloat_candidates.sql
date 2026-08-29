with params as (
  select
    current_setting('block_size')::numeric as bs,
    24::numeric as page_hdr,
    16::numeric as btree_special,
    8::int as ma
),
candidates_bounded as (
  select
    i.oid,
    i.relname as index_name,
    i.relpages,
    i.reltuples,
    am.amname,
    n.nspname as index_schema,
    t.relname as table_name,
    tn.nspname as table_schema,
    coalesce(substring(array_to_string(i.reloptions, ' ') from 'fillfactor=([0-9]+)')::numeric, 90) as fillfactor
  from pg_catalog.pg_class i
  join pg_catalog.pg_index x on x.indexrelid = i.oid
  join pg_catalog.pg_namespace n on n.oid = i.relnamespace
  join pg_catalog.pg_class t on t.oid = x.indrelid
  join pg_catalog.pg_namespace tn on tn.oid = t.relnamespace
  join pg_catalog.pg_am am on am.oid = i.relam
  where i.relkind = 'i'
    and i.relpages >= 1280
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by i.relpages desc, i.oid
  limit 501
),
coverage as (
  select (select count(*) > 500 from candidates_bounded) as candidate_sample_truncated
),
candidates as (
  select * from candidates_bounded limit 500
),
index_column_stats as (
  select
    cand.oid as relid,
    count(a.attnum)::int as index_columns,
    count(coalesce(ts.avg_width, xs.avg_width))::int as stats_columns,
    coalesce(sum(
      (1 - coalesce(ts.null_frac, xs.null_frac, 0)) * coalesce(ts.avg_width, xs.avg_width, 0)
    ), 0) as data_width,
    coalesce(max(coalesce(ts.null_frac, xs.null_frac, 0)), 0) as max_null_frac
  from candidates cand
  join pg_catalog.pg_attribute a on a.attrelid = cand.oid and a.attnum > 0
  left join pg_catalog.pg_stats ts
    on ts.schemaname = cand.table_schema
    and ts.tablename = cand.table_name
    and ts.attname = a.attname
    and not ts.inherited
  left join pg_catalog.pg_stats xs
    on xs.schemaname = cand.index_schema
    and xs.tablename = cand.index_name
    and xs.attname = a.attname
  group by cand.oid
),
computed as (
  select
    cand.*,
    ics.index_columns,
    ics.stats_columns,
    ics.data_width,
    p.bs,
    p.ma,
    p.page_hdr,
    p.btree_special,
    (8 + case when ics.max_null_frac > 0 then (ics.index_columns + 7) / 8 else 0 end) as itup_hdr_raw
  from candidates cand
  join index_column_stats ics on ics.relid = cand.oid
  cross join params p
),
sized as (
  select
    with_hdr.*,
    (itup_hdr_aligned + ceil(data_width) + (ma - (ceil(data_width)::int % ma)) % ma + 4)::numeric as tuple_size,
    (amname = 'btree' and reltuples > 0 and data_width > 0 and stats_columns >= index_columns) as can_estimate
  from (
    select
      computed.*,
      (itup_hdr_raw + (ma - itup_hdr_raw % ma) % ma)::numeric as itup_hdr_aligned
    from computed
  ) with_hdr
),
estimated as (
  select
    *,
    case
      when not can_estimate then null
      else 1 + ceil(
        reltuples / greatest(floor(((bs - page_hdr - btree_special) * fillfactor / 100) / tuple_size), 1)
      )
    end as expected_pages
  from sized
)
select
  e.index_schema as schema_name,
  e.index_name,
  e.oid::int8 as index_oid,
  e.table_schema || '.' || e.table_name as table_name,
  e.amname as index_type,
  (e.relpages::numeric * e.bs)::int8 as index_bytes,
  e.reltuples::int8 as row_estimate,
  e.fillfactor::int8 as fillfactor,
  case when e.expected_pages is null then null
    else (least(e.expected_pages, e.relpages::numeric) * e.bs)::int8 end as expected_bytes,
  case when e.expected_pages is null then null
    else (greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs)::int8 end as wasted_bytes,
  case when e.expected_pages is null then null
    else (greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages)::float8 end as bloat_percent,
  si.idx_scan::int8 as index_scans,
  e.can_estimate,
  case
    when e.amname <> 'btree' then 'Bloat estimation supports btree indexes only'
    when e.reltuples <= 0 then 'No row statistics; run ANALYZE on the table first'
    when e.data_width <= 0 or e.stats_columns < e.index_columns
      then 'Statistics are missing for ' || (e.index_columns - e.stats_columns)::text
        || ' of ' || e.index_columns::text || ' indexed columns; run ANALYZE or grant access to pg_stats'
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
    when not e.can_estimate then 'Bloat cannot be estimated for this index'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 60
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 5368709120
      then 'Estimated bloat exceeds 60% and 5 GiB; this is a statistical estimate - verify before planning REINDEX CONCURRENTLY'
    when greatest(e.relpages::numeric - e.expected_pages, 0) * 100 / e.relpages >= 40
      and greatest(e.relpages::numeric - e.expected_pages, 0) * e.bs >= 1073741824
      then 'Estimated bloat exceeds 40% and 1 GiB; this is a statistical estimate - verify before acting'
    else ''
  end as risk_reason
from estimated e
left join pg_catalog.pg_stat_user_indexes si on si.indexrelid = e.oid
cross join coverage
order by wasted_bytes desc nulls last, schema_name, index_name
