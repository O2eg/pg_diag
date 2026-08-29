with publications_bounded as (
  select
    p.oid,
    p.pubname,
    p.pubowner,
    p.puballtables,
    p.pubinsert,
    p.pubupdate,
    p.pubdelete,
    null::boolean as pubtruncate,
    null::boolean as pubviaroot
  from pg_catalog.pg_publication p
  order by p.pubname, p.oid
  limit 1001
),
publications as (
  select * from publications_bounded limit 1000
),
publication_tables_bounded as (
  select r.prpubid
  from pg_catalog.pg_publication_rel r
  join publications p on p.oid = r.prpubid
  order by r.prpubid, r.prrelid
  limit 10001
),
publication_tables as (
  select * from publication_tables_bounded limit 10000
),
table_counts as (
  select prpubid, count(*)::int8 as sampled_table_count
  from publication_tables
  group by prpubid
),
coverage as (
  select
    (select count(*) > 1000 from publications_bounded) as result_truncated,
    (select count(*) > 10000 from publication_tables_bounded) as table_sample_truncated
)
select
  p.pubname::text as publication_name,
  pg_catalog.pg_get_userbyid(p.pubowner)::text as owner_name,
  p.pubowner::int8 as owner_oid,
  coalesce(r.rolcanlogin, false) as owner_can_login,
  coalesce(r.rolsuper, false) as owner_is_superuser,
  p.puballtables as all_tables,
  p.pubinsert as publishes_insert,
  p.pubupdate as publishes_update,
  p.pubdelete as publishes_delete,
  p.pubtruncate as publishes_truncate,
  p.pubviaroot as publish_via_partition_root,
  coalesce(t.sampled_table_count, 0)::int8 as sampled_table_count,
  coverage.result_truncated,
  coverage.table_sample_truncated,
  case
    when coverage.result_truncated or coverage.table_sample_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.result_truncated
      then 'More than 1000 publications exist; the list is partial'
    when coverage.table_sample_truncated
      then 'More than 10000 publication table memberships exist; sampled table counts are partial'
    else ''
  end as pg_diag_internal_reason
from publications p
left join pg_catalog.pg_roles r on r.oid = p.pubowner
left join table_counts t on t.prpubid = p.oid
cross join coverage
order by publication_name
