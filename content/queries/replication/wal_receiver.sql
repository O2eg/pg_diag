select current_database() as datname,
case status when 'stopped' then 0 when 'starting' then 1 when 'streaming' then 2 when 'waiting' then 3 when 'restarting' then 4 when 'stopping' then 5 else -1 end as status,
      (receive_start_lsn- '0/0') % (2^52)::bigint as receive_start_lsn,
      receive_start_tli,
      (flushed_lsn- '0/0') % (2^52)::bigint as flushed_lsn,
      received_tli,
      extract(epoch from last_msg_send_time) as last_msg_send_time,
      extract(epoch from last_msg_receipt_time) as last_msg_receipt_time,
      (latest_end_lsn - '0/0') % (2^52)::bigint as latest_end_lsn,
      extract(epoch from latest_end_time) as latest_end_time,
      substring(slot_name from 'repmgr_slot_([0-9]*)') as upstream_node,
      trim(both '''' from substring(conninfo from 'host=([^ ]*)')) as upstream_host,
      slot_name
  from pg_catalog.pg_stat_wal_receiver
