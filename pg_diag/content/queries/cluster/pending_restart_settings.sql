select
  name,
  setting,
  unit,
  source,
  sourcefile,
  sourceline,
  short_desc
from pg_settings
where pending_restart
order by name asc
