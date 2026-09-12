with file_entries as (
  select
    f.name,
    f.setting as file_value,
    f.error as file_error
  from pg_catalog.pg_file_settings f
  where f.seqno = (
    select max(inner_f.seqno)
    from pg_catalog.pg_file_settings inner_f
    where inner_f.name = f.name
  )
)
select
  s.name,
  s.setting,
  s.unit,
  s.source,
  s.sourcefile,
  s.sourceline,
  s.short_desc,
  s.boot_val,
  fe.file_value,
  fe.file_error,
  case
    -- The server replaced the file's "auto" sentinel (equal to boot_val, typically -1) with a
    -- value it computed at startup: pg_settings.source says 'override'. Every reload compares
    -- the file value with the computed one and raises pending_restart again, and a restart
    -- recomputes the same value. A file value that merely returns a setting to its default
    -- (source 'configuration file' / 'command line' / ...) is a real change and stays
    -- 'configuration_change'.
    when s.source = 'override' and fe.file_value = s.boot_val then 'auto_computed_artifact'
    else 'configuration_change'
  end as pending_restart_kind
from pg_catalog.pg_settings s
left join file_entries fe on fe.name = s.name
where s.pending_restart
order by pending_restart_kind asc, s.name asc
