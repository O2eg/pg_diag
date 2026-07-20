select
  name,
  default_version,
  installed_version,
  case when installed_version is null then false else true end as installed,
  comment
from pg_available_extensions
order by installed desc, name asc
