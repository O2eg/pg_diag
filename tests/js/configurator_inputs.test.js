'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {prepare} = require('../../src/pg_diag/render/configurator/inputs.js');
const GiB = 1024 ** 3;
const table = data => ({collection_status: 'ok', result: {kind: 'table',
  columns: Object.keys(data[0] || {}).map(name => ({name})), rows: data}});
const plain = data => ({collection_status: 'ok', result: {kind: 'plain_text', data}});
function artifact() {
  return {runtime: {server_version_num: 180004}, items: {
    'os.cpu_info': plain('CPU(s): 16\nOn-line CPU(s) list: 0-7,12-15\n'),
    'os.kernel_version': plain('Linux server 6.8'),
    'os.total_ram': table([{total_ram_bytes: String(64 * GiB)}]),
    'os.memory_info': table([{metric: 'MemAvailable', value_normalized: 1024, unit_normalized: 'bytes'}]),
    'os.lshw_disk': table([{logicalname: '/dev/nvme0n1', description: 'NVMe disk'}]),
    'os.disk_usage': table([{filesystem: '/dev/nvme0n1p1', mount_point: '/', available_bytes: 100 * GiB}]),
    'overview.pg_settings': table([
      {setting_name: 'data_directory', setting_value: '/srv/postgres', source_unit: null},
      {setting_name: 'max_connections', setting_value: '100', source_unit: null},
      {setting_name: 'autovacuum_max_workers', setting_value: '3', source_unit: null},
      {setting_name: 'shared_buffers', setting_value: '1024', source_unit: '8kB'},
      {setting_name: 'wal_level', setting_value: 'replica', source_unit: null},
      {setting_name: 'archive_mode', setting_value: 'off', source_unit: null},
      {setting_name: 'synchronous_standby_names', setting_value: '', source_unit: null},
      {setting_name: 'custom.extension', setting_value: 'a,"b"\n</script><script>alert(1)</script>', source_unit: null},
    ]),
  }};
}
function library() {
  const html = fs.readFileSync(path.join(__dirname, '../../src/pg_diag/render/vendor/pg-configurator.html'), 'utf8');
  const payload = id => JSON.parse(html.match(new RegExp(`<script type="application/json" id="${id}">(.*?)</script>`, 's'))[1]).payload;
  const js = html.match(/<script type="module">(.*?)<\/script>/s)[1];
  const core = js.slice(0, js.lastIndexOf('const readJson ='));
  const context = {};
  vm.runInNewContext(core + '\nthis.api = {makeConf, createEnums, parseUserConfig, diffConfigurations, loadSettingMetadata};', context);
  const rules = payload('pgc-rules'), pgSettings = payload('pgc-pg-settings'), schema = payload('pgc-input-schema');
  return {...context.api, rules, pgSettings, schema};
}
const lib = library();
function generate(prepared) {
  const opts = Object.fromEntries(lib.schema.options.filter(o => o.role === 'calculation' && Object.hasOwn(prepared.inputs, o.dest))
    .map(o => [o.make_conf_parameter, prepared.inputs[o.dest]]));
  const {cpu_cores, ram_value, ...rest} = opts;
  return lib.makeConf(cpu_cores, ram_value, rest, {...lib, enums: lib.createEnums(lib.rules.enums)});
}
test('capacity comes from online CPUs and total RAM, not utilization, free RAM or collector host', () => {
  const a = artifact(); a.runtime.cpu_count = 1024;
  const p = prepare(a);
  assert.equal(p.ready, true); assert.equal(p.inputs.db_cpu, '12');
  assert.equal(p.inputs.db_ram, String(64 * GiB)); assert.equal(p.inputs.db_disk_type, 'NVME');
  assert.equal(p.inputs.max_conns, 100); assert.equal(p.inputs.min_conns, 100);
  const result = generate(p); assert.equal(String(result.config.max_connections), '100');
  assert.ok(Object.keys(result.parameters).length > 30);
});
test('all settings survive CSV roundtrip, including units, empty values, quotes and multiline extension values', () => {
  const a = artifact(), p = prepare(a), parsed = lib.parseUserConfig(p.currentConfig);
  assert.equal(parsed.entries.size, 8); assert.equal(parsed.skipped, 0);
  assert.equal(parsed.entries.get('shared_buffers').unit, '8kB');
  assert.equal(parsed.entries.get('custom.extension').value, a.items['overview.pg_settings'].result.rows[7].setting_value);
  assert.equal(parsed.entries.get('synchronous_standby_names').value, '');
  const meta = lib.loadSettingMetadata(lib.pgSettings, '18');
  const diff = lib.diffConfigurations({shared_buffers: {value: '8MB', context: 'postmaster'}}, parsed.entries, meta);
  assert.equal(diff.matching, 1);
});
test('missing/invalid required measurements hide availability instead of selecting browser defaults', () => {
  for (const id of ['os.cpu_info', 'os.total_ram', 'os.lshw_disk', 'overview.pg_settings', 'os.kernel_version']) {
    const a = artifact(); delete a.items[id];
    if (id === 'os.lshw_disk') a.items['os.disk_usage'].result.rows[0].filesystem = '/dev/mapper/data';
    assert.equal(prepare(a).ready, false, id);
  }
  for (const val of [null, '', 'NaN', 'Infinity', -1, true]) {
    const a = artifact(); a.items['os.total_ram'].result.rows[0].total_ram_bytes = val;
    assert.equal(prepare(a).ready, false, String(val));
  }
  const a = artifact(); a.runtime.server_version_num = 190000; assert.equal(prepare(a).ready, false);
  a.runtime.server_version_num = 180004; a.items['overview.pg_settings'].result.row_count = 99;
  assert.equal(prepare(a).ready, false);
});
test('explicit cgroup quota/cpuset and memory limits constrain host values, unlimited sentinels do not', () => {
  const a = artifact(); a.items['os.resource_limits'] = table([{cpu_quota_us: 150000, cpu_period_us: 100000,
    cpuset_cpus_effective: '0-3', memory_limit_bytes: 4 * GiB}]);
  let p = prepare(a); assert.equal(p.inputs.db_cpu, '1.5'); assert.equal(p.inputs.db_ram, String(4 * GiB));
  generate(p);
  a.items['os.resource_limits'] = table([{cpu_quota_us: -1, cpu_period_us: 100000, memory_limit_bytes: 2 ** 63}]);
  p = prepare(a); assert.equal(p.inputs.db_cpu, '12'); assert.equal(p.inputs.db_ram, String(64 * GiB));
  // several postmasters in different cgroups: no limit can be attributed to this database
  a.items['os.resource_limits'] = table([
    {scope: 'postmaster', cgroup_count: 2, cpu_quota_us: 150000, cpu_period_us: 100000, memory_limit_bytes: 4 * GiB},
    {scope: 'postmaster', cgroup_count: 2, cpu_quota_us: 50000, cpu_period_us: 100000, memory_limit_bytes: 2 * GiB}]);
  p = prepare(a); assert.equal(p.ready, false, 'host capacity never substitutes an unknown container limit');
  assert.equal(p.inputs.db_cpu, undefined); assert.equal(p.inputs.db_ram, undefined);
  assert.ok(p.missing.some(n => /several PostgreSQL postmasters/.test(n)));
  // limits of the collector's own cgroup (no postmaster visible) are not database limits
  a.items['os.resource_limits'] = table([{scope: 'collector', cgroup_count: 0, cpu_quota_us: 150000, cpu_period_us: 100000, memory_limit_bytes: 4 * GiB}]);
  p = prepare(a); assert.equal(p.inputs.db_cpu, '12'); assert.equal(p.inputs.db_ram, String(64 * GiB));
});
test('mounted database storage wins over unrelated disks and unresolved mixed inventories stay unavailable', () => {
  const a = artifact(); a.items['os.lshw_disk'].result.rows.push({logicalname: '/dev/sda', description: 'SATA disk'});
  assert.equal(prepare(a).inputs.db_disk_type, 'NVME');
  a.items['os.disk_usage'].result.rows[0].filesystem = 'overlay';
  assert.equal(prepare(a).ready, false);
  a.items['os.lshw_disk'].result.rows.pop();
  const p = prepare(a); assert.equal(p.ready, true); assert.ok(p.notes.some(n => n.startsWith('Container filesystem')));
  assert.equal(p.sources.find(s => s.field === 'db_disk_type').confidence, 'inferred');
});
test('database volumes and replication entities are deduplicated; cumulative WAL is not a measured rate', () => {
  const a = artifact();
  a.items['overview.database_volume'] = table([{database_name:'db',database_size_bytes: 2 * GiB, subscriptions:2},
    {database_name:'db',database_size_bytes: 2 * GiB, subscriptions:2}, {database_name:'db2',database_size_bytes: GiB, subscriptions:0}]);
  a.items['replication.replication_slots'] = table([{slot_name:'p', slot_type:'physical',active_pid:1}, {slot_name:'l', slot_type:'logical',active_pid:2}]);
  a.items['replication.physical_replication'] = table([{pid:1}, {pid:2}]);
  a.items['replication.subscription_workers'] = table([{subid:4,pid:1}, {subid:4,pid:2}]);
  a.items['snapshot_charts_db.wal_growth_rate'] = {collection_status:'ok',result:{kind:'chart',series:[{unit:'bytes', points:[{value:100000}]}]}};
  let p=prepare(a); assert.equal(p.inputs.db_size, String(3 * GiB)); assert.equal(p.inputs.replica_count,1);
  assert.equal(p.inputs.logical_subscription_count,2); assert.equal(p.inputs.replication_mode,'logical');
  assert.equal(p.inputs.peak_wal_rate,undefined); generate(p);
  a.items['snapshot_charts_db.wal_growth_rate'].result.series[0] = {unit:'bytes/s', points:[{value:null},{value:0},{value:100.9},{value:50}]};
  p=prepare(a); assert.equal(p.inputs.peak_wal_rate,'101');
});
test('compact reports with matrix rows are supported and errored items cannot supply capacity', () => {
  const a=artifact();
  for (const item of Object.values(a.items)) if (item.result.kind === 'table')
    item.result.rows=item.result.rows.map(r=>item.result.columns.map(c=>r[c.name]));
  assert.equal(prepare(a).ready,true);
  a.items['os.cpu_info'].collection_status='error'; assert.equal(prepare(a).ready,false);
});
test('WAL allowance follows a collected symlink to the WAL filesystem and rejects zero free space', () => {
  const a=artifact(); a.items['os.symlinks_in_sensitive_paths']=table([{path:'/srv/postgres/pg_wal',target:'/wal'}]);
  a.items['os.disk_usage'].result.rows.push({filesystem:'/dev/nvme1n1',mount_point:'/wal',available_bytes:8*GiB});
  let p=prepare(a);assert.equal(p.inputs.wal_disk_budget,String(2*GiB));
  assert.ok(p.sources.find(s=>s.field==='wal_disk_budget').itemIds.includes('os.symlinks_in_sensitive_paths'));
  a.items['os.disk_usage'].result.rows[1].available_bytes=0;p=prepare(a);assert.equal(p.ready,false);
});
test('LOAD-only auto_explain availability comes from preloaded modules, not pg_available_extensions', () => {
  const a=artifact();a.items['cluster_inventory.extensions']=table([{name:'pg_stat_statements'}]);
  let p=prepare(a);assert.equal(p.inputs.available_extensions,undefined); generate(p);
  a.items['overview.pg_settings'].result.rows.push({setting_name:'shared_preload_libraries',setting_value:'auto_explain,pg_stat_statements'});
  p=prepare(a); assert.ok(p.inputs.available_extensions.includes('auto_explain'));generate(p);
});
test('network filesystem metadata takes precedence over local NVMe inventory', () => {
  const a=artifact();a.items['os.disk_usage'].result.rows[0].filesystem='10.0.0.1:/postgres';
  a.items['os.mounts']=plain('10.0.0.1:/postgres on / type nfs4 (rw,relatime)');
  assert.equal(prepare(a).inputs.db_disk_type,'NETWORK');
});
