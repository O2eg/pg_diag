select
  oid::int8 as tablespace_oid,
  spcname as tablespace_name,
  pg_get_userbyid(spcowner) as owner,
  pg_tablespace_location(oid) as location,
  pg_tablespace_size(oid)::int8 as size_bytes
from pg_tablespace
order by size_bytes desc, tablespace_name asc
