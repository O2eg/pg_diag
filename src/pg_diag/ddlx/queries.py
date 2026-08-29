"""Read-only catalog queries for DDL extraction.

Every query is a single SELECT bounded by an oid array parameter ($1),
following the pg_dump pattern of one query per catalog for the whole
object set.  Server deparse functions (pg_get_expr, pg_get_constraintdef,
pg_get_indexdef, pg_get_viewdef, pg_get_triggerdef, pg_get_functiondef,
pg_get_partkeydef) and quote_ident/quote_literal do all quoting
server-side; the client only concatenates.

To keep round trips at one per extractor call even on high-latency links,
sectioned_sql() combines several of these queries into a single UNION ALL
statement whose rows are (section, to_jsonb(row)::text) pairs sharing the
same $1 oid array; dependent filters ("columns of the tables among $1",
"functions of the triggers on $1") are expressed as subselects so the
server resolves the dependency chain inside the one statement.
"""

from __future__ import annotations

from typing import Sequence

PG12 = 120000
PG11 = 110000
PG15 = 150000
PG16 = 160000
PG17 = 170000


def sectioned_sql(sections: Sequence[tuple[str, str]]) -> str:
    """Combine per-catalog queries into one statement returning tagged jsonb rows."""
    parts = [
        f"select '{name}'::text as section, to_jsonb(q)::text as payload\nfrom (\n{sql}) q"
        for name, sql in sections
    ]
    return "\nunion all\n".join(parts)


def relations_sql(server_version_num: int, *, tables_only: bool = False) -> str:
    if server_version_num >= PG12:
        has_oids = "false as relhasoids"
    else:
        has_oids = "c.relhasoids"
    table_filter = "\n  and c.relkind in ('r', 'p', 'f')" if tables_only else ""
    return f"""
select
  c.oid::int8 as oid,
  c.relkind::text as relkind,
  c.relpersistence::text as relpersistence,
  c.oid::regclass::text as identifier,
  c.reltype::int8 as reltype,
  c.relispartition,
  c.relispopulated,
  {has_oids},
  pg_catalog.pg_get_expr(c.relpartbound, c.oid) as partition_bound,
  case when c.relkind in ('p', 'I') then pg_catalog.pg_get_partkeydef(c.oid) end
    as partition_key,
  case when c.reloftype <> 0 then c.reloftype::regtype::text end as of_type,
  pg_catalog.array_to_string(c.reloptions, ', ') as reloptions,
  am.amname::text as access_method,
  quote_ident(ts.spcname) as tablespace,
  case when c.relkind in ('v', 'm') then pg_catalog.pg_get_viewdef(c.oid, true) end
    as view_definition,
  case when c.relkind in ('i', 'I') then pg_catalog.pg_get_indexdef(c.oid) end
    as index_definition,
  (select string_agg(i.inhparent::regclass::text, ', ' order by i.inhseqno)
     from pg_catalog.pg_inherits i
    where i.inhrelid = c.oid) as parents,
  quote_ident(fs.srvname) as foreign_server,
  (select string_agg(quote_ident(o.option_name) || ' ' || quote_literal(o.option_value), ', ')
     from pg_catalog.pg_options_to_table(ft.ftoptions) o) as foreign_options_sql
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
left join pg_catalog.pg_am am on am.oid = c.relam
left join pg_catalog.pg_tablespace ts on ts.oid = c.reltablespace
left join pg_catalog.pg_foreign_table ft on ft.ftrelid = c.oid
left join pg_catalog.pg_foreign_server fs on fs.oid = ft.ftserver
where c.oid = any($1::oid[]){table_filter}
"""


def columns_sql(server_version_num: int, *, of_types: bool = False) -> str:
    if server_version_num >= PG12:
        generated = "a.attgenerated::text as generated"
    else:
        generated = "''::text as generated"
    if of_types:
        relation_filter = (
            "a.attrelid in (select tt.typrelid from pg_catalog.pg_type tt\n"
            "                where tt.oid = any($1::oid[]))"
        )
    else:
        relation_filter = "a.attrelid = any($1::oid[])"
    return f"""
select
  a.attrelid::int8 as table_oid,
  a.attnum::int as attnum,
  quote_ident(a.attname) as name_q,
  pg_catalog.format_type(a.atttypid, a.atttypmod) as type_name,
  a.attnotnull as not_null,
  a.attislocal as is_local,
  a.attidentity::text as identity,
  {generated},
  case when a.atthasdef then pg_catalog.pg_get_expr(d.adbin, d.adrelid) end as default_expr,
  case when a.attcollation <> 0 and a.attcollation is distinct from t.typcollation then
    (select quote_ident(cn.nspname) || '.' || quote_ident(co.collname)
       from pg_catalog.pg_collation co
       join pg_catalog.pg_namespace cn on cn.oid = co.collnamespace
      where co.oid = a.attcollation)
  end as collation_sql,
  (select string_agg(quote_ident(o.option_name) || ' ' || quote_literal(o.option_value), ', ')
     from pg_catalog.pg_options_to_table(a.attfdwoptions) o) as fdw_options_sql
from pg_catalog.pg_attribute a
left join pg_catalog.pg_type t on t.oid = a.atttypid
left join pg_catalog.pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
where {relation_filter}
  and a.attnum > 0
  and not a.attisdropped
order by a.attrelid, a.attnum
"""


_CONSTRAINT_SELECT = """
select
  c.oid::int8 as oid,
  c.conrelid::int8 as table_oid,
  c.contypid::int8 as domain_oid,
  quote_ident(c.conname) as name_q,
  c.contype::text as contype,
  c.conislocal as is_local,
  pg_catalog.pg_get_constraintdef(c.oid) as definition,
  case when c.conrelid <> 0 then c.conrelid::regclass::text end as table_identifier,
  case when c.contypid <> 0 then c.contypid::regtype::text end as domain_identifier
from pg_catalog.pg_constraint c
"""


def constraints_by_oid_sql() -> str:
    return _CONSTRAINT_SELECT + "where c.oid = any($1::oid[])\n"


def constraints_for_tables_sql() -> str:
    return _CONSTRAINT_SELECT + "where c.conrelid = any($1::oid[])\norder by c.conrelid, c.oid\n"


def constraints_for_domains_sql() -> str:
    return _CONSTRAINT_SELECT + "where c.contypid = any($1::oid[])\norder by c.contypid, c.oid\n"


def sequences_sql() -> str:
    return """
select
  s.seqrelid::int8 as oid,
  pg_catalog.format_type(s.seqtypid, null) as data_type,
  s.seqstart as start_value,
  s.seqincrement as increment,
  s.seqmin as min_value,
  s.seqmax as max_value,
  s.seqcache as cache_size,
  s.seqcycle as cycle,
  (select quote_ident(dn.nspname) || '.' || quote_ident(dc.relname)
            || '.' || quote_ident(da.attname)
     from pg_catalog.pg_depend d
     join pg_catalog.pg_class dc on dc.oid = d.refobjid
     join pg_catalog.pg_namespace dn on dn.oid = dc.relnamespace
     join pg_catalog.pg_attribute da
       on da.attrelid = d.refobjid and da.attnum = d.refobjsubid
    where d.classid = 'pg_catalog.pg_class'::regclass
      and d.objid = s.seqrelid
      and d.refclassid = 'pg_catalog.pg_class'::regclass
      and d.refobjsubid > 0
      and d.deptype in ('a', 'i')
    limit 1) as owned_by
from pg_catalog.pg_sequence s
where s.seqrelid = any($1::oid[])
"""


def functions_sql(server_version_num: int, *, of_table_triggers: bool = False) -> str:
    if server_version_num >= PG11:
        prokind = "p.prokind::text as prokind"
        guard = "p.prokind in ('f', 'p', 'w')"
    else:
        prokind = (
            "case when p.proisagg then 'a' when p.proiswindow then 'w' else 'f' end as prokind"
        )
        guard = "not p.proisagg"
    if of_table_triggers:
        where = (
            "p.oid in (select tg.tgfoid from pg_catalog.pg_trigger tg\n"
            "           where tg.tgrelid = any($1::oid[]) and not tg.tgisinternal)"
        )
    else:
        where = "p.oid = any($1::oid[])"
    return f"""
select
  p.oid::int8 as oid,
  p.oid::regprocedure::text as identifier,
  {prokind},
  case when {guard} then pg_catalog.pg_get_functiondef(p.oid) end as definition
from pg_catalog.pg_proc p
where {where}
"""


_TRIGGER_SELECT = """
select
  t.oid::int8 as oid,
  t.tgrelid::int8 as table_oid,
  t.tgfoid::int8 as function_oid,
  quote_ident(t.tgname) as name_q,
  t.tgrelid::regclass::text as table_identifier,
  pg_catalog.pg_get_triggerdef(t.oid, true) as definition,
  t.tgenabled::text as enabled
from pg_catalog.pg_trigger t
"""


def triggers_by_oid_sql() -> str:
    return _TRIGGER_SELECT + "where t.oid = any($1::oid[]) and not t.tgisinternal\n"


def triggers_for_tables_sql() -> str:
    return (
        _TRIGGER_SELECT
        + "where t.tgrelid = any($1::oid[]) and not t.tgisinternal\n"
        + "order by t.tgrelid, t.tgname\n"
    )


def indexes_for_tables_sql() -> str:
    return """
select
  i.indexrelid::int8 as oid,
  i.indrelid::int8 as table_oid,
  i.indexrelid::regclass::text as identifier,
  pg_catalog.pg_get_indexdef(i.indexrelid) as index_definition,
  i.indisvalid as is_valid,
  exists (
    select 1 from pg_catalog.pg_constraint con
    where con.conindid = i.indexrelid
      and con.conrelid = i.indrelid
  ) as backs_constraint
from pg_catalog.pg_index i
where i.indrelid = any($1::oid[])
order by i.indrelid, i.indexrelid
"""


def databases_sql(server_version_num: int) -> str:
    if server_version_num >= PG17:
        provider = (
            "case d.datlocprovider when 'i' then 'icu' when 'b' then 'builtin' end"
            " as locale_provider,\n  d.datlocale::text as provider_locale,\n"
            "  d.daticurules::text as icu_rules"
        )
    elif server_version_num >= PG16:
        provider = (
            "case d.datlocprovider when 'i' then 'icu' end as locale_provider,\n"
            "  d.daticulocale::text as provider_locale,\n  d.daticurules::text as icu_rules"
        )
    elif server_version_num >= PG15:
        provider = (
            "case d.datlocprovider when 'i' then 'icu' end as locale_provider,\n"
            "  d.daticulocale::text as provider_locale,\n  null::text as icu_rules"
        )
    else:
        provider = (
            "null::text as locale_provider,\n  null::text as provider_locale,\n"
            "  null::text as icu_rules"
        )
    return f"""
select
  d.oid::int8 as oid,
  d.datname::text as identifier,
  quote_ident(d.datname) as name_q,
  pg_catalog.pg_encoding_to_char(d.encoding)::text as encoding,
  d.datcollate::text as lc_collate,
  d.datctype::text as lc_ctype,
  {provider},
  d.datconnlimit::int as connection_limit,
  d.datallowconn as allow_connections,
  d.datistemplate as is_template,
  (select quote_ident(ts.spcname)
     from pg_catalog.pg_tablespace ts
    where ts.oid = d.dattablespace
      and ts.spcname <> 'pg_default') as tablespace,
  (select string_agg(
            'ALTER DATABASE ' || quote_ident(d.datname) || ' SET '
              || split_part(cfg.item, '=', 1) || ' TO '
              || {_SETTING_VALUE_SQL} || ';',
            E'\n')
     from pg_catalog.pg_db_role_setting s
     cross join lateral unnest(s.setconfig) cfg(item)
    where s.setdatabase = d.oid
      and s.setrole = 0) as settings_sql
from pg_catalog.pg_database d
where d.oid = any($1::oid[])
"""


SENSITIVE_SETTING_REGEX = "(password|passwd|secret|token|apikey|api_key|credential|dsn|conninfo)"

_SETTING_VALUE_SQL = (
    "case when split_part(cfg.item, '=', 1) ~* '" + SENSITIVE_SETTING_REGEX + "'\n"
    "                   then quote_literal('[REDACTED]')\n"
    "                   else quote_literal(substring(cfg.item from strpos(cfg.item, '=') + 1))\n"
    "              end"
)


def roles_sql(server_version_num: int) -> str:
    """Role attributes without any password material (pg_roles only)."""
    if server_version_num >= PG16:
        membership_options = (
            "' WITH ADMIN ' || case when m.admin_option then 'TRUE' else 'FALSE' end\n"
            "              || ', INHERIT ' || case when m.inherit_option then 'TRUE'"
            " else 'FALSE' end\n"
            "              || ', SET ' || case when m.set_option then 'TRUE' else 'FALSE' end"
            " || ';'"
        )
    else:
        membership_options = (
            "case when m.admin_option then ' WITH ADMIN OPTION;' else ';' end"
        )
    return f"""
select
  r.oid::int8 as oid,
  r.rolname::text as identifier,
  quote_ident(r.rolname) as name_q,
  r.rolsuper as is_superuser,
  r.rolinherit as inherit,
  r.rolcreaterole as create_role,
  r.rolcreatedb as create_db,
  r.rolcanlogin as can_login,
  r.rolreplication as replication,
  r.rolbypassrls as bypass_rls,
  r.rolconnlimit::int as connection_limit,
  case when r.rolvaliduntil is not null and r.rolvaliduntil <> 'infinity'
       then r.rolvaliduntil::text end as valid_until,
  (select string_agg(
            'GRANT ' || quote_ident(g.rolname) || ' TO ' || quote_ident(r.rolname)
              || {membership_options},
            E'\n' order by g.rolname)
     from pg_catalog.pg_auth_members m
     join pg_catalog.pg_roles g on g.oid = m.roleid
    where m.member = r.oid) as memberships_sql,
  (select string_agg(
            'ALTER ROLE ' || quote_ident(r.rolname)
              || case when s.setdatabase <> 0
                      then ' IN DATABASE ' || quote_ident(d.datname)
                      else '' end
              || ' SET ' || split_part(cfg.item, '=', 1) || ' TO '
              || {_SETTING_VALUE_SQL} || ';',
            E'\n')
     from pg_catalog.pg_db_role_setting s
     left join pg_catalog.pg_database d on d.oid = s.setdatabase
     cross join lateral unnest(s.setconfig) cfg(item)
    where s.setrole = r.oid) as settings_sql
from pg_catalog.pg_roles r
where r.oid = any($1::oid[])
"""


def tablespaces_sql() -> str:
    return """
select
  t.oid::int8 as oid,
  t.spcname::text as identifier,
  quote_ident(t.spcname) as name_q,
  pg_catalog.pg_tablespace_location(t.oid)::text as location,
  pg_catalog.array_to_string(t.spcoptions, ', ') as options
from pg_catalog.pg_tablespace t
where t.oid = any($1::oid[])
"""


def types_sql(*, of_composite_relations: bool = False) -> str:
    if of_composite_relations:
        where = (
            "t.oid in (select c2.reltype from pg_catalog.pg_class c2\n"
            "           where c2.oid = any($1::oid[]) and c2.relkind = 'c')"
        )
    else:
        where = "t.oid = any($1::oid[])"
    return f"""
select
  t.oid::int8 as oid,
  t.typtype::text as typtype,
  t.oid::regtype::text as identifier,
  t.typrelid::int8 as typrelid,
  t.typnotnull as domain_not_null,
  case when t.typtype = 'd' then pg_catalog.format_type(t.typbasetype, t.typtypmod) end
    as domain_base,
  case when t.typtype = 'd' then t.typdefault end as domain_default,
  case when t.typtype = 'd' and t.typcollation <> 0
            and t.typcollation is distinct from bt.typcollation then
    (select quote_ident(cn.nspname) || '.' || quote_ident(co.collname)
       from pg_catalog.pg_collation co
       join pg_catalog.pg_namespace cn on cn.oid = co.collnamespace
      where co.oid = t.typcollation)
  end as domain_collation_sql,
  case when t.typtype = 'e' then
    (select string_agg(quote_literal(e.enumlabel), E',\n    ' order by e.enumsortorder)
       from pg_catalog.pg_enum e
      where e.enumtypid = t.oid)
  end as enum_labels,
  case when t.typtype = 'r' then
    (select pg_catalog.format_type(r.rngsubtype, null)
       from pg_catalog.pg_range r
      where r.rngtypid = t.oid)
  end as range_subtype,
  case when t.typtype = 'r' then
    (select quote_ident(oc.opcname)
       from pg_catalog.pg_range r
       join pg_catalog.pg_opclass oc on oc.oid = r.rngsubopc
      where r.rngtypid = t.oid
        and not oc.opcdefault)
  end as range_subtype_opclass,
  case when t.typtype = 'r' then
    (select r.rngcanonical::regproc::text
       from pg_catalog.pg_range r
      where r.rngtypid = t.oid
        and r.rngcanonical <> 0)
  end as range_canonical,
  case when t.typtype = 'r' then
    (select r.rngsubdiff::regproc::text
       from pg_catalog.pg_range r
      where r.rngtypid = t.oid
        and r.rngsubdiff <> 0)
  end as range_subtype_diff,
  case when t.typtype = 'r' then
    (select quote_ident(cn.nspname) || '.' || quote_ident(co.collname)
       from pg_catalog.pg_range r
       join pg_catalog.pg_collation co on co.oid = r.rngcollation
       join pg_catalog.pg_namespace cn on cn.oid = co.collnamespace
      where r.rngtypid = t.oid
        and r.rngcollation <> 0)
  end as range_collation_sql
from pg_catalog.pg_type t
left join pg_catalog.pg_type bt on bt.oid = t.typbasetype
where {where}
"""
