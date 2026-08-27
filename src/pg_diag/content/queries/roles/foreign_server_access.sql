with wrappers_bounded as (
  select w.oid, w.fdwname, w.fdwowner, w.fdwacl
  from pg_catalog.pg_foreign_data_wrapper w
  order by w.fdwname, w.oid
  limit 201
),
wrappers as (
  select * from wrappers_bounded limit 200
),
servers_bounded as (
  select s.oid, s.srvname, s.srvfdw, s.srvowner, s.srvacl
  from pg_catalog.pg_foreign_server s
  order by s.srvname, s.oid
  limit 1001
),
servers as (
  select * from servers_bounded limit 1000
),
wrapper_grants_bounded as (
  select
    'foreign data wrapper'::text as object_kind,
    w.fdwname::text as object_name,
    null::text as wrapper_name,
    pg_catalog.pg_get_userbyid(w.fdwowner)::text as owner_name,
    e.grantee,
    e.privilege_type::text as privilege_type,
    e.is_grantable,
    (w.fdwacl is null) as acl_is_default,
    null::text as mapping_option_names,
    null::boolean as mapping_options_visible
  from wrappers w
  cross join lateral aclexplode(coalesce(w.fdwacl, acldefault('F', w.fdwowner))) e
  where e.grantee <> w.fdwowner
  limit 1001
),
wrapper_grants as (
  select * from wrapper_grants_bounded limit 1000
),
server_grants_bounded as (
  select
    'foreign server'::text as object_kind,
    s.srvname::text as object_name,
    w.fdwname::text as wrapper_name,
    pg_catalog.pg_get_userbyid(s.srvowner)::text as owner_name,
    e.grantee,
    e.privilege_type::text as privilege_type,
    e.is_grantable,
    (s.srvacl is null) as acl_is_default,
    null::text as mapping_option_names,
    null::boolean as mapping_options_visible
  from servers s
  left join pg_catalog.pg_foreign_data_wrapper w on w.oid = s.srvfdw
  cross join lateral aclexplode(coalesce(s.srvacl, acldefault('S', s.srvowner))) e
  where e.grantee <> s.srvowner
  limit 1001
),
server_grants as (
  select * from server_grants_bounded limit 1000
),
mappings_bounded as (
  select
    'user mapping'::text as object_kind,
    um.srvname::text as object_name,
    w.fdwname::text as wrapper_name,
    pg_catalog.pg_get_userbyid(s.srvowner)::text as owner_name,
    um.umuser as grantee,
    'USER MAPPING'::text as privilege_type,
    false as is_grantable,
    false as acl_is_default,
    (
      select string_agg(split_part(o.entry, '=', 1), ', ' order by split_part(o.entry, '=', 1))
      from unnest(um.umoptions) o(entry)
    ) as mapping_option_names,
    (um.umoptions is not null) as mapping_options_visible
  from pg_catalog.pg_user_mappings um
  join servers s on s.oid = um.srvid
  left join pg_catalog.pg_foreign_data_wrapper w on w.oid = s.srvfdw
  order by um.srvname, um.umuser
  limit 1001
),
mappings as (
  select * from mappings_bounded limit 1000
),
findings as (
  select * from wrapper_grants
  union all
  select * from server_grants
  union all
  select * from mappings
),
coverage as (
  select
    (
      (select count(*) > 200 from wrappers_bounded)
      or (select count(*) > 1000 from servers_bounded)
    ) as candidate_sample_truncated,
    (
      (select count(*) > 1000 from wrapper_grants_bounded)
      or (select count(*) > 1000 from server_grants_bounded)
      or (select count(*) > 1000 from mappings_bounded)
    ) as acl_expansion_truncated
)
select
  f.object_kind,
  f.object_name,
  f.wrapper_name,
  f.owner_name,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  f.privilege_type,
  f.is_grantable,
  f.acl_is_default,
  f.mapping_option_names,
  f.mapping_options_visible,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
      then 'Foreign data wrapper, server, or mapping sample was truncated; foreign access is partial'
    else ''
  end as pg_diag_internal_reason
from findings f
left join pg_catalog.pg_roles gr on gr.oid = f.grantee
cross join coverage
union all
select
  'coverage'::text,
  '[coverage]'::text,
  null::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  false,
  null::text,
  null::boolean,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  'unknown'::text,
  'Foreign data wrapper, server, or mapping sample was truncated; an empty result is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
order by object_kind, object_name, grantee_name, privilege_type
