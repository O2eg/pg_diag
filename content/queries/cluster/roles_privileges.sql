select
  rolname,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  rolcanlogin,
  rolconnlimit,
  rolvaliduntil
from pg_roles
where rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls
order by rolsuper desc, rolcreaterole desc, rolcreatedb desc, rolreplication desc, rolname asc
