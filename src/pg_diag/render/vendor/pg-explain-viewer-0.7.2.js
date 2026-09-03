/*
 * pgplan.js — PostgreSQL query plan parser + analyzer.
 *
 * Pure JS, zero dependencies, browser + node (UMD-lite).
 * Accepts EXPLAIN [ANALYZE] output in text, JSON or YAML format,
 * including auto_explain log messages ("duration: N ms  plan: ...")
 * with an optional "Query Text:" preamble.
 *
 * Everything is normalized to the text representation first (JSON/YAML
 * are converted to canonical text), then a single text parser builds
 * the node tree and the analyzer computes derived metrics:
 *   - inclusive / exclusive time per node (parallel-aware)
 *   - exclusive buffers / IO timings (PG reports them inclusive)
 *   - planned-vs-actual rows ratio
 *   - per-metric maxima and plan totals for heat scaling
 *
 * API:
 *   PgPlan.parse(input) -> Plan | throws Error
 *   Plan = {
 *     nodes: [Node...],        // in plan-text order, node.id = index
 *     text: string,            // canonical plan text (without query)
 *     query: string|null,      // Query Text if present
 *     duration: number|null,   // "duration: N ms" prefix if present
 *     format: 'text'|'json'|'yaml',
 *     ext: [ExtLine...],       // Planning Time / Execution Time / JIT / ...
 *     triggers: [...],
 *     executionTime, planningTime,   // ms or null
 *     totals: {time, rows, rowsRemoved, buffers:{}, ioRead, ioWrite},
 *     max: {...},              // maxima used for heat scaling
 *     columns: {...},          // which optional columns carry data
 *     diagnostics: [{code, severity, message, count, nodes?/samples?}],
 *     truncated: boolean,      // plan tail/head cut off; advice disabled
 *     advice: [{code, sev, obs, hyp, next, nodes, ext?, idxs?,
 *               impact: {ms, pct, level high|medium|low|minor|unknown}}],
 *     coaching: [{option, reason, warning}], // missing EXPLAIN options
 *   }
 *   Node.workers = [{num, timeTotal, rows, loops, buf, ...}] when the plan
 *   carries per-worker "Worker N:" blocks.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./pgplan-expr.js'), require('./pgplan-sql.js'));
  } else {
    // both peers are optional in the browser
    root.PgPlan = factory(root.PgPlanExpr, root.PgPlanSql);
  }
}(typeof self !== 'undefined' ? self : this, function (Expr, Sql) {
  'use strict';

  const BUFFER_COLS = [
    'shared-hit', 'shared-read', 'shared-dirtied', 'shared-written',
    'local-hit', 'local-read', 'local-dirtied', 'local-written',
    'temp-read', 'temp-written',
  ];

  const round3 = v => Math.round(v * 1000) / 1000;

  /* ------------------------------------------------------------------ *
   * Input normalization
   * ------------------------------------------------------------------ */

  const HTML_ENTITIES = {
    '&nbsp;': ' ', '&amp;': '&', '&quot;': '"', '&apos;': "'",
    '&lt;': '<', '&gt;': '>', '&#x27;': "'", '&#39;': "'",
  };

  function preclean(input) {
    let s = String(input == null ? '' : input);
    s = s.replace(/\r\n?/g, '\n').replace(/ /g, ' ');
    if (/&(?:nbsp|amp|quot|apos|lt|gt|#x27|#39);/.test(s)) {
      s = s.replace(/&(?:nbsp|amp|quot|apos|lt|gt|#x27|#39);/g, m => HTML_ENTITIES[m] || m);
    }
    // whole-input CSV quoting: "..."" escaped
    const t = s.trim();
    if (t.length > 2 && t[0] === '"' && t.endsWith('"') && !t.slice(1, -1).includes('\n"')) {
      const inner = t.slice(1, -1);
      if (inner.includes('""')) s = inner.replace(/""/g, '"');
    }
    return s;
  }

  // "2026-08-31 ... LOG:  duration: 24.339 ms  plan:" or "duration: 24.339 ms  plan:"
  const RE_DURATION = /^.*?duration: ([\d.]+) ms\s+plan:\s*$/;

  /* ------------------------------------------------------------------ *
   * YAML (auto_explain / EXPLAIN FORMAT YAML) — minimal indent parser,
   * enough for the fixed structure EXPLAIN emits.
   * ------------------------------------------------------------------ */

  function yamlScalar(v) {
    const s = v.trim();
    if (s.startsWith('"') && s.endsWith('"') && s.length > 1) {
      // PostgreSQL emits YAML strings via escape_json() (explain.c
      // escape_yaml), so double-quoted scalars are JSON-compatible —
      // JSON.parse decodes \" \\ \n \uXXXX correctly
      try { return JSON.parse(s); } catch (e) { return s.slice(1, -1); }
    }
    if (s === 'true') return true;
    if (s === 'false') return false;
    if (s === 'null' || s === '~') return null;
    const n = Number(s);
    return Number.isNaN(n) ? s : n;
  }

  function parseYaml(text) {
    const lines = text.split('\n')
      .filter(l => l.trim().length)
      .map(l => {
        const indent = l.search(/\S/);
        let body = l.slice(indent);
        let item = false;
        if (body.startsWith('- ')) { item = true; body = body.slice(2); }
        else if (body === '-') { item = true; body = ''; }
        return { indent, item, body };
      });

    let pos = 0;

    function parseBlock(minIndent, asList) {
      const out = asList ? [] : {};
      while (pos < lines.length) {
        const ln = lines[pos];
        if (ln.indent < minIndent) break;
        if (asList) {
          if (!ln.item || ln.indent !== minIndent) break;
          pos++;
          // scalar item ("- amount DESC" / "- \"o.id\"") vs map item
          // ("- Node Type: ..." plus following deeper keys)
          const isMapEntry = /^("(?:[^"]|"")*"|[^:]+):(?:\s|$)/.test(ln.body);
          const hasChildKeys = pos < lines.length && !lines[pos].item
            && lines[pos].indent === minIndent + 2;
          if (!isMapEntry && !hasChildKeys) {
            out.push(yamlScalar(ln.body));
            continue;
          }
          const obj = {};
          consumeEntry(obj, ln.body, ln.indent + 2);
          // more keys of the same map at indent+2
          while (pos < lines.length && !lines[pos].item && lines[pos].indent === minIndent + 2) {
            const l2 = lines[pos]; pos++;
            consumeEntry(obj, l2.body, l2.indent + 2);
          }
          out.push(obj);
        } else {
          if (ln.item || ln.indent !== minIndent) break;
          pos++;
          consumeEntry(out, ln.body, ln.indent + 2);
        }
      }
      return out;
    }

    function consumeEntry(map, body, childIndent) {
      const m = /^("(?:[^"]|"")*"|[^:]+):(.*)$/.exec(body);
      if (!m) return;
      const key = m[1].replace(/^"|"$/g, '');
      const val = m[2];
      if (val.trim() === '') {
        // nested list or map
        if (pos < lines.length && lines[pos].indent >= childIndent) {
          map[key] = lines[pos].item
            ? parseBlock(lines[pos].indent, true)
            : parseBlock(lines[pos].indent, false);
        } else {
          map[key] = null;
        }
      } else {
        map[key] = yamlScalar(val);
      }
    }

    return parseBlock(lines.length ? lines[0].indent : 0, lines.length ? lines[0].item : false);
  }

  /* ------------------------------------------------------------------ *
   * JSON plan -> canonical text  (single parsing path for all formats)
   * ------------------------------------------------------------------ */

  const AGG_STRATEGY = {
    Hashed: 'HashAggregate', Sorted: 'GroupAggregate',
    Mixed: 'MixedAggregate', Plain: 'Aggregate',
  };

  // Keywords PostgreSQL reserves (reserved + type_func_name categories):
  // they cannot appear as bare identifiers in DDL/relation positions.
  // Keep in sync with the copy in pgplan-expr.js.
  const SQL_RESERVED = new Set(('all analyse analyze and any array as asc asymmetric authorization'
    + ' binary both case cast check collate collation column concurrently constraint create'
    + ' cross current_catalog current_date current_role current_schema current_time'
    + ' current_timestamp current_user default deferrable desc distinct do else end except'
    + ' false fetch for foreign freeze from full grant group having ilike in initially inner'
    + ' intersect into is isnull join lateral leading left like limit localtime localtimestamp'
    + ' natural not notnull null offset on only or order outer overlaps placing primary'
    + ' references returning right select session_user similar some symmetric table tablesample'
    + ' then to trailing true union unique user using variadic verbose when where window with')
    .split(' '));

  const RE_SIMPLE_NAME = /^[a-z_][a-z0-9_$]*$/;
  const quoteIdent = s => (RE_SIMPLE_NAME.test(String(s)) && !SQL_RESERVED.has(String(s))
    ? s : '"' + String(s).replace(/"/g, '""') + '"');

  const fmtNum = v => (typeof v === 'number' && !Number.isInteger(v) ? String(v) : String(v));

  // Keys consumed structurally by nodeToText — everything else falls through
  // to the generic "Key: value" emitter so nothing silently disappears.
  const NODE_KEYS_HANDLED = new Set([
    'Node Type', 'Parent Relationship', 'Subplan Name', 'Parallel Aware', 'Async Capable',
    'Partial Mode', 'Strategy', 'Command', 'Join Type', 'Operation', 'Custom Plan Provider',
    'Scan Direction', 'Index Name', 'CTE Name', 'Relation Name', 'Schema', 'Function Name',
    'Alias', 'Startup Cost', 'Total Cost', 'Plan Rows', 'Plan Width',
    'Actual Startup Time', 'Actual Total Time', 'Actual Rows', 'Actual Loops',
    'Plans', 'Workers', 'Disabled',
    'WAL Records', 'WAL FPI', 'WAL Bytes',
    'Sort Method', 'Sort Space Used', 'Sort Space Type',
    'Hash Buckets', 'Original Hash Buckets', 'Hash Batches', 'Original Hash Batches',
    'Cache Hits', 'Cache Misses', 'Cache Evictions', 'Cache Overflows',
    'Peak Memory Usage', 'Exact Heap Blocks', 'Lossy Heap Blocks',
    'Shared Hit Blocks', 'Shared Read Blocks', 'Shared Dirtied Blocks', 'Shared Written Blocks',
    'Local Hit Blocks', 'Local Read Blocks', 'Local Dirtied Blocks', 'Local Written Blocks',
    'Temp Read Blocks', 'Temp Written Blocks',
    'I/O Read Time', 'I/O Write Time',
    'Shared I/O Read Time', 'Shared I/O Write Time',
    'Local I/O Read Time', 'Local I/O Write Time',
    'Temp I/O Read Time', 'Temp I/O Write Time',
  ]);

  function bufSegment(node, kind) {
    const parts = [];
    for (const type of ['Hit', 'Read', 'Dirtied', 'Written']) {
      const key = kind + ' ' + type + ' Blocks';
      if (node[key]) parts.push(type.toLowerCase() + '=' + node[key]);
    }
    return parts.length ? kind.toLowerCase().replace(' i/o', '') + ' ' + parts.join(' ') : null;
  }

  function nodeToText(node, out, indent, headless) {
    node = Object.assign({}, node);
    delete node['Parent Relationship'];

    if (node['Subplan Name']) {
      out.push(indent + node['Subplan Name']);
      delete node['Subplan Name'];
      nodeToText(node, out, indent + '  ');
      return;
    }

    if (!headless) {
      const head = [];
      let pfx = indent && node['Node Type'] ? indent + '->  ' : indent;
      if (node['Parallel Aware']) head.push('Parallel');
      if (node['Async Capable']) head.push('Async');
      if (node['Partial Mode'] && node['Partial Mode'] !== 'Simple') head.push(node['Partial Mode']);

      const nt = node['Node Type'];
      if (nt === 'Aggregate' && node['Strategy']) {
        head.push(AGG_STRATEGY[node['Strategy']] || 'Aggregate');
      } else if (nt === 'SetOp') {
        head.push((node['Strategy'] === 'Hashed' ? 'Hash' : '') + 'SetOp ' + (node['Command'] || ''));
      } else if (node['Join Type'] && node['Join Type'] !== 'Inner') {
        if (nt === 'Nested Loop') head.push(nt + ' ' + node['Join Type'] + ' Join');
        else head.push(nt.replace(/ Join$/, '') + ' ' + node['Join Type'] + ' Join');
      } else if (nt === 'ModifyTable') {
        head.push(node['Operation']);
      } else if (nt === 'Custom Scan' && node['Custom Plan Provider']) {
        head.push('Custom Scan (' + node['Custom Plan Provider'] + ')');
      } else {
        head.push(nt);
      }

      if (node['Scan Direction'] && node['Scan Direction'] !== 'Forward'
          && node['Scan Direction'] !== 'NoMovement') {
        head.push(node['Scan Direction']);
      }

      let rel = null;
      if (node['Index Name']) {
        head.push((nt === 'Bitmap Index Scan' ? 'on ' : 'using ') + quoteIdent(node['Index Name']));
      }
      if (node['CTE Name']) { rel = node['CTE Name']; head.push('on ' + quoteIdent(rel)); }
      if (node['Relation Name']) {
        rel = node['Relation Name'];
        head.push('on ' + (node['Schema'] ? quoteIdent(node['Schema']) + '.' : '') + quoteIdent(rel));
      }
      if (node['Function Name']) {
        rel = node['Function Name'];
        head.push('on ' + (node['Schema'] && node['Schema'] !== 'pg_catalog'
          ? quoteIdent(node['Schema']) + '.' : '') + quoteIdent(rel));
      }
      if (node['Alias'] && node['Alias'] !== rel) {
        head.push((nt === 'Subquery Scan' ? 'on ' : '') + quoteIdent(node['Alias']));
      }

      let line = pfx + head.filter(Boolean).join(' ');
      if (node['Total Cost'] !== undefined) {
        line += '  (cost=' + Number(node['Startup Cost']).toFixed(2)
          + '..' + Number(node['Total Cost']).toFixed(2)
          + ' rows=' + node['Plan Rows'] + ' width=' + node['Plan Width'] + ')';
      }
      if (node['Actual Loops'] !== undefined) {
        if (node['Actual Loops'] === 0) {
          line += ' (never executed)';
        } else {
          line += ' (actual'
            + (node['Actual Total Time'] !== undefined
              ? ' time=' + Number(node['Actual Startup Time']).toFixed(3)
                + '..' + Number(node['Actual Total Time']).toFixed(3)
              : '')
            + ' rows=' + node['Actual Rows'] + ' loops=' + node['Actual Loops'] + ')';
        }
      }
      out.push(line);
    }

    const attr = indent === '' ? '  ' : indent + '      ';

    // ordered structured attributes
    for (const [key, val] of Object.entries(node)) {
      if (/ Key$/.test(key) || key === 'Order By' || key === 'Output'
          || key === 'Group By' || key === 'Partition By') {
        out.push(attr + key + ': ' + (Array.isArray(val) ? val.join(', ') : val));
        delete node[key];
      }
    }
    if (node['Sort Method']) {
      out.push(attr + 'Sort Method: ' + node['Sort Method']
        + '  ' + (node['Sort Space Type'] || 'Memory') + ': ' + node['Sort Space Used'] + 'kB');
    }
    if (node['Hash Buckets'] !== undefined) {
      let l = attr + 'Buckets: ' + node['Hash Buckets'];
      if (node['Original Hash Buckets']) l += ' (originally ' + node['Original Hash Buckets'] + ')';
      l += '  Batches: ' + node['Hash Batches'];
      if (node['Original Hash Batches']) l += ' (originally ' + node['Original Hash Batches'] + ')';
      l += '  Memory Usage: ' + node['Peak Memory Usage'] + 'kB';
      out.push(l);
      delete node['Peak Memory Usage'];
    }
    if (node['Cache Hits'] !== undefined) {
      out.push(attr + 'Hits: ' + node['Cache Hits']
        + '  Misses: ' + (node['Cache Misses'] || 0)
        + '  Evictions: ' + (node['Cache Evictions'] || 0)
        + '  Overflows: ' + (node['Cache Overflows'] || 0)
        + '  Memory Usage: ' + (node['Peak Memory Usage'] || 0) + 'kB');
      delete node['Peak Memory Usage'];
    }
    for (const [key, val] of Object.entries(node)) {
      if (/ Cond$/.test(key)) { out.push(attr + key + ': ' + val); delete node[key]; }
    }
    for (const [key, val] of Object.entries(node)) {
      if ((/Filter$/.test(key) || / Recheck$/.test(key)) && !key.startsWith('Rows Removed')) {
        out.push(attr + key + ': ' + val);
        delete node[key];
      }
    }
    for (const [key, val] of Object.entries(node)) {
      if (key.startsWith('Rows Removed by')) {
        if (val) out.push(attr + key + ': ' + val);
        delete node[key];
      }
    }
    if (node['Exact Heap Blocks'] || node['Lossy Heap Blocks']) {
      out.push(attr + 'Heap Blocks:'
        + (node['Exact Heap Blocks'] ? ' exact=' + node['Exact Heap Blocks'] : '')
        + (node['Lossy Heap Blocks'] ? ' lossy=' + node['Lossy Heap Blocks'] : ''));
    }
    if (node['WAL Records'] || node['WAL FPI'] || node['WAL Bytes']) {
      const seg = [];
      if (node['WAL Records']) seg.push('records=' + node['WAL Records']);
      if (node['WAL FPI']) seg.push('fpi=' + node['WAL FPI']);
      if (node['WAL Bytes']) seg.push('bytes=' + node['WAL Bytes']);
      out.push(attr + 'WAL: ' + seg.join(' '));
    }
    if (node['Shared Hit Blocks'] !== undefined) {
      const segs = [bufSegment(node, 'Shared'), bufSegment(node, 'Local'), bufSegment(node, 'Temp')]
        .filter(Boolean);
      if (segs.length) out.push(attr + 'Buffers: ' + segs.join(', '));
    }
    // I/O timings: plain (<= PG14) or split shared/local/temp (PG15+)
    {
      const io = [];
      const plainR = node['I/O Read Time'], plainW = node['I/O Write Time'];
      if (plainR) io.push('read=' + Number(plainR).toFixed(3));
      if (plainW) io.push('write=' + Number(plainW).toFixed(3));
      const parts = [];
      if (io.length) parts.push(io.join(' '));
      for (const kind of ['Shared', 'Local', 'Temp']) {
        const r = node[kind + ' I/O Read Time'], w = node[kind + ' I/O Write Time'];
        const seg = [];
        if (r) seg.push('read=' + Number(r).toFixed(3));
        if (w) seg.push('write=' + Number(w).toFixed(3));
        if (seg.length) parts.push(kind.toLowerCase() + ' ' + seg.join(' '));
      }
      if (parts.length) out.push(attr + 'I/O Timings: ' + parts.join(', '));
    }
    if (node['Disabled'] === true) out.push(attr + 'Disabled: true');

    // generic fallback for anything not consumed (keeps PG18+ additions visible)
    for (const [key, val] of Object.entries(node)) {
      if (NODE_KEYS_HANDLED.has(key)) continue;
      if (val === null || val === undefined || val === false || val === 0 || val === '') continue;
      if (typeof val === 'object') {
        // nested structures (Grouping Sets, Full-sort Groups, ...) have no
        // generic text representation yet — record the loss instead of
        // dropping it silently
        if (key !== 'Workers' && key !== 'Plans' && out.skipped) out.skipped.push(key);
        continue;
      }
      out.push(attr + key + ': ' + fmtNum(val));
    }

    if (Array.isArray(node['Workers'])) {
      node['Workers'].forEach(w => {
        const wc = Object.assign({}, w);
        const n = wc['Worker Number']; delete wc['Worker Number'];
        const sub = [];
        nodeToText(wc, sub, '', true);
        if (wc['Actual Loops'] !== undefined) {
          sub.unshift('actual time=' + Number(wc['Actual Startup Time']).toFixed(3)
            + '..' + Number(wc['Actual Total Time']).toFixed(3)
            + ' rows=' + wc['Actual Rows'] + ' loops=' + wc['Actual Loops']);
        }
        sub.forEach((l, i) => out.push(attr + (i === 0 ? 'Worker ' + n + ': ' + l.trim() : '  ' + l.trim())));
      });
    }

    if (Array.isArray(node['Plans'])) {
      node['Plans'].forEach(child =>
        nodeToText(child, out, indent === '' ? '  ' : indent + '      '));
    }
  }

  function jsonToText(json) {
    const rootObj = Array.isArray(json) ? json[0] : json;
    if (!rootObj || typeof rootObj !== 'object' || !rootObj['Plan']) {
      throw new Error('JSON plan: no "Plan" key found');
    }
    const out = [];
    out.skipped = []; // structured keys with no text representation
    nodeToText(rootObj['Plan'], out, '');

    if (rootObj['Settings'] && typeof rootObj['Settings'] === 'object') {
      out.push('Settings: ' + Object.entries(rootObj['Settings'])
        .map(([k, v]) => k + " = '" + v + "'").join(', '));
    }
    if (rootObj['Planning'] && typeof rootObj['Planning'] === 'object') {
      out.push('Planning:');
      nodeToText(Object.assign({}, rootObj['Planning']), out, '', true);
    }
    if (rootObj['Planning Time'] !== undefined) {
      out.push('Planning Time: ' + Number(rootObj['Planning Time']).toFixed(3) + ' ms');
    }
    if (Array.isArray(rootObj['Triggers'])) {
      rootObj['Triggers'].forEach(t => out.push(
        'Trigger ' + t['Trigger Name']
        + (t['Relation'] ? ' on ' + t['Relation'] : '')
        + ': time=' + Number(t['Time']).toFixed(3) + ' calls=' + t['Calls']));
    }
    if (rootObj['JIT'] && typeof rootObj['JIT'] === 'object') {
      const jit = rootObj['JIT'];
      out.push('JIT:');
      if (jit['Functions'] !== undefined) out.push('  Functions: ' + jit['Functions']);
      if (jit['Options']) {
        out.push('  Options: ' + Object.entries(jit['Options'])
          .map(([k, v]) => k + ' ' + (v ? 'true' : 'false')).join(', '));
      }
      if (jit['Timing']) {
        out.push('  Timing: ' + Object.entries(jit['Timing'])
          .map(([k, v]) => k + ' ' + Number(v).toFixed(3) + ' ms').join(', '));
      }
    }
    // PG17+: serialization of the result set
    if (rootObj['Serialization'] && typeof rootObj['Serialization'] === 'object') {
      const ser = rootObj['Serialization'];
      const parts = [];
      if (ser['Time'] !== undefined) parts.push('time=' + Number(ser['Time']).toFixed(3) + ' ms');
      if (ser['Output Volume'] !== undefined) parts.push('output=' + ser['Output Volume'] + 'kB');
      if (ser['Format'] !== undefined) parts.push('format=' + ser['Format']);
      if (parts.length) out.push('Serialization: ' + parts.join('  '));
      const segs = [bufSegment(ser, 'Shared'), bufSegment(ser, 'Local'), bufSegment(ser, 'Temp')]
        .filter(Boolean);
      if (segs.length) out.push('  Buffers: ' + segs.join(', '));
    }
    if (rootObj['Execution Time'] !== undefined) {
      out.push('Execution Time: ' + Number(rootObj['Execution Time']).toFixed(3) + ' ms');
    }
    if (rootObj['Query Identifier'] !== undefined && rootObj['Query Identifier'] !== null) {
      out.push('Query Identifier: ' + rootObj['Query Identifier']);
    }
    return {
      text: out.join('\n'),
      query: rootObj['Query Text'] !== undefined ? String(rootObj['Query Text']) : null,
      skipped: out.skipped,
    };
  }

  /* ------------------------------------------------------------------ *
   * Text plan parser
   * ------------------------------------------------------------------ */

  // identifier reference as EXPLAIN prints it: dot-separated parts, each
  // either quoted (embedded quotes doubled: "we""ird") or bare; covers
  // public."Mixed Case" and "*SELECT* 1"-style aliases
  const IDENT_PART = '(?:"(?:[^"]|"")+"|[\\w$*]+)';
  const IDENT = '(?:' + IDENT_PART + '(?:\\.' + IDENT_PART + ')*)';
  const RE_COST = /\s\(cost=([\d.]+)\.\.([\d.]+) rows=([\d.]+) width=(\d+)\)/;
  const RE_ACTUAL = /\s?\(actual(?: time=([\d.]+)\.\.([\d.]+))? rows=([\d.]+) loops=([\d.]+)\)/;
  // running-query snapshot (pg_query_state "in progress"):
  // (Current loop: [actual time=a..b] [actual] rows=N, loop number=M)
  const RE_CURRENT = /\s?\(Current loop: (?:actual time=([\d.]+)\.\.([\d.]+),? )?(?:actual )?rows=([\d.]+), loop number=(\d+)\)/;
  const RE_NEVER = /\s?\(never executed\)/;

  const RE_SPEC = /^(CTE|InitPlan|SubPlan)\b(.*)$/;
  const RE_TRIGGER = /^Trigger\s+(.+?):\s+time=([\d.]+)\s+calls=(\d+)\s*$/;
  const RE_WORKER_HEAD = /^Worker (\d+):\s*(.*)$/;
  const RE_WORKER_ACTUAL = /^actual(?: time=([\d.]+)\.\.([\d.]+))? rows=([\d.]+) loops=([\d.]+)$/;
  const RE_ATTR = /^([A-Za-z][A-Za-z0-9 _\/\-().]*?):(?: (.*))?$/;

  const RE_HEAD_INDEX = new RegExp('^(.*?[Ss]can(?: Backward)?) using (' + IDENT + ') on (' + IDENT + ')(?: (' + IDENT + '))?$');
  const RE_HEAD_BIS = new RegExp('^(.*?Bitmap Index Scan) on (' + IDENT + ')$');
  const RE_HEAD_SCAN = new RegExp('^(.*?(?:[Ss]can(?: Backward)?|Sample Scan)) on (' + IDENT + ')(?: (' + IDENT + '))?$');
  const RE_HEAD_DML = new RegExp('^((?:Foreign )?(?:Insert|Update|Delete|Merge)) on (' + IDENT + ')(?: (' + IDENT + '))?$');
  const RE_HEAD_CUSTOM = /^(Custom Scan) \(([^)]+)\)(?: on (.*))?$/;
  const RE_HEAD_FUNC = new RegExp('^(Function Scan|Table Function Scan) on (' + IDENT + ')(?: (' + IDENT + '))?$');

  // Root-level lines that are not plan nodes
  const EXT_HEADS = new Set([
    'Planning Time', 'Planning', 'Execution Time', 'Total Runtime', 'JIT',
    'Settings', 'Query Identifier', 'Serialization',
  ]);

  // strip outer quotes and undouble embedded ones ("we""ird" -> we"ird)
  const unquote = s => (s && s.length > 2 && s[0] === '"' && s.endsWith('"')
    ? s.slice(1, -1).replace(/""/g, '"') : s);

  function parseNodeHead(head, node) {
    let m;
    // relation: display name (unquoted); relationRef: reference exactly as
    // printed in the plan (quotes intact) — required for safe generated DDL,
    // where "a.b" (one dotted name) and a.b (schema.rel) must stay distinct
    if ((m = RE_HEAD_BIS.exec(head))) {
      node.rawType = m[1]; node.index = unquote(m[2]);
    } else if ((m = RE_HEAD_INDEX.exec(head))) {
      node.rawType = m[1]; node.index = unquote(m[2]);
      node.relation = unquote(m[3]); node.relationRef = m[3];
      node.alias = m[4] ? unquote(m[4]) : null;
    } else if ((m = RE_HEAD_CUSTOM.exec(head))) {
      node.rawType = m[1] + ' (' + m[2] + ')';
      node.relation = m[3] ? unquote(m[3]) : null;
      node.relationRef = m[3] || null;
    } else if ((m = RE_HEAD_DML.exec(head))) {
      node.rawType = m[1]; node.relation = unquote(m[2]); node.relationRef = m[2];
      node.alias = m[3] ? unquote(m[3]) : null;
    } else if ((m = RE_HEAD_FUNC.exec(head)) || (m = RE_HEAD_SCAN.exec(head))) {
      node.rawType = m[1]; node.relation = unquote(m[2]); node.relationRef = m[2];
      node.alias = m[3] ? unquote(m[3]) : null;
    } else {
      node.rawType = head;
    }
    node.nodeType = node.rawType.replace(/^(Parallel|Partial|Finalize|Async)\s+/, '');
  }

  // Buffers: shared hit=1 read=2, local hit=3, temp read=4 written=5
  function parseBuffers(val, node) {
    for (const seg of val.split(',')) {
      const parts = seg.trim().split(/\s+/);
      let kind = 'shared';
      let i = 0;
      if (parts[0] === 'shared' || parts[0] === 'local' || parts[0] === 'temp') {
        kind = parts[0]; i = 1;
      }
      for (; i < parts.length; i++) {
        const kv = parts[i].split('=');
        if (kv.length !== 2) continue;
        const type = kv[0] === 'written' ? 'written' : kv[0];
        const key = kind + '-' + type;
        const n = Number(kv[1]);
        if (!Number.isNaN(n) && BUFFER_COLS.includes(key)) {
          node.buf[key] = (node.buf[key] || 0) + n;
        }
      }
    }
  }

  // I/O Timings: read=1.1 write=2.2 | shared read=.. write=.., temp read=..
  function parseIoTimings(val, node) {
    for (const seg of val.split(',')) {
      const parts = seg.trim().split(/\s+/);
      for (const p of parts) {
        const kv = p.split('=');
        if (kv.length !== 2) continue;
        const n = Number(kv[1]);
        if (Number.isNaN(n)) continue;
        if (kv[0] === 'read') node.ioRead = round3((node.ioRead || 0) + n);
        else if (kv[0] === 'write') node.ioWrite = round3((node.ioWrite || 0) + n);
      }
    }
  }

  // "quicksort  Memory: 25kB" / "external merge  Disk: 3320kB"
  function parseSortMethod(val, target) {
    target.sortMethod = val;
    const sm = /^(.*?)\s+(Memory|Disk):\s*(\d+)kB/.exec(val);
    if (sm) {
      target.sortMethod = sm[1];
      target.sortSpace = sm[2];
      target.sortSizeKb = Number(sm[3]);
    }
  }

  const FILTER_ATTRS = new Set([
    'Filter', 'Join Filter', 'One-Time Filter', 'Conflict Filter',
    'Index Cond', 'Hash Cond', 'Merge Cond', 'Recheck Cond', 'TID Cond', 'Order By',
  ]);

  function applyAttr(node, key, val) {
    switch (key) {
      case 'Buffers': parseBuffers(val, node); return;
      case 'I/O Timings': parseIoTimings(val, node); return;
      case 'Workers Planned': node.workersPlanned = Number(val); return;
      case 'Workers Launched': node.workersLaunched = Number(val); return;
      case 'Heap Fetches': node.heapFetches = Number(val); return;
      case 'Subplans Removed': node.subplansRemoved = Number(val); return;
      case 'Sort Method': parseSortMethod(val, node); return;
      case 'Heap Blocks': {
        const ex = /exact=(\d+)/.exec(val);
        const lo = /lossy=(\d+)/.exec(val);
        if (ex) node.heapBlocksExact = Number(ex[1]);
        if (lo) node.heapBlocksLossy = Number(lo[1]);
        return;
      }
      case 'Buckets':   // "1024 (originally 512)  Batches: 1  Memory Usage: 32kB"
      case 'Batches': { // "1  Memory Usage: 32kB  Disk Usage: 40kB"
        const du = /Disk Usage: (\d+)kB/.exec(val);
        if (du) node.diskUsageKb = Number(du[1]);
        const mu = /Memory Usage: (\d+)kB/.exec(val);
        if (mu) node.memUsageKb = Number(mu[1]);
        // Batches > 1 is how a hash join reports that the hash side did not
        // fit into work_mem: it was partitioned to temp files. "(originally
        // N)" means the planner's size estimate was corrected at run time.
        const lead = /^(\d+)(?:\s*\(originally (\d+)\))?/.exec(val);
        if (key === 'Buckets' && lead) {
          node.hashBuckets = Number(lead[1]);
          if (lead[2]) node.hashBucketsOrig = Number(lead[2]);
        }
        const ba = key === 'Batches' ? lead
          : /Batches: (\d+)(?:\s*\(originally (\d+)\))?/.exec(val);
        if (ba) {
          node.hashBatches = Number(ba[1]);
          if (ba[2]) node.hashBatchesOrig = Number(ba[2]);
        }
        return;
      }
      // Memoize: "Hits: 5  Misses: 2  Evictions: 0  Overflows: 0  Memory Usage: 1kB"
      case 'Hits': {
        const num = re => { const m = re.exec(val); return m ? Number(m[1]) : 0; };
        node.cache = {
          hits: num(/^(\d+)/),
          misses: num(/Misses: (\d+)/),
          evictions: num(/Evictions: (\d+)/),
          overflows: num(/Overflows: (\d+)/),
        };
        const mu2 = /Memory Usage: (\d+)kB/.exec(val);
        if (mu2) node.memUsageKb = Number(mu2[1]);
        return;
      }
      case 'Sort Key': node.sortKey = val; return;
      case 'Group Key': node.groupKey = val; return;
    }
    if (key === 'Disk Usage') { node.diskUsageKb = parseInt(val, 10) || 0; return; }
    if (key.startsWith('Rows Removed by')) {
      const n = Number(val);
      if (!Number.isNaN(n)) {
        node.rowsRemoved += n;
        node.rowsRemovedBy[key.slice('Rows Removed by '.length)] = n;
      }
      return;
    }
    if (FILTER_ATTRS.has(key) && (key.endsWith('Filter') || key.endsWith('Cond'))) {
      node.filters.push({ key, val });
    }
  }

  // Per-worker statistics live in "Worker N:" blocks whose sub-lines repeat
  // node attributes (Buffers, I/O Timings, Sort Method, an "actual ..."
  // clause). The node-level numbers already include the workers, so these
  // lines must NOT be re-applied to the node — they are parsed into
  // node.workers[] instead.
  function makeWorker(num) {
    return {
      num,
      timeStartup: null, timeTotal: null, rows: null, loops: null,
      buf: {}, ioRead: 0, ioWrite: 0,
      sortMethod: null, sortSpace: null, sortSizeKb: null,
    };
  }

  function applyWorkerLine(w, text) {
    const am = RE_WORKER_ACTUAL.exec(text);
    if (am) {
      if (am[1] !== undefined) {
        w.timeStartup = Number(am[1]);
        w.timeTotal = Number(am[2]);
      }
      w.rows = Number(am[3]);
      w.loops = Number(am[4]);
      return;
    }
    const m = RE_ATTR.exec(text);
    if (!m) return;
    const val = m[2] !== undefined ? m[2] : '';
    switch (m[1]) {
      case 'Buffers': parseBuffers(val, w); break;
      case 'I/O Timings': parseIoTimings(val, w); break;
      case 'Sort Method': parseSortMethod(val, w); break;
      // anything else stays visible via the node's raw detail lines
    }
  }

  function makeNode(id) {
    return {
      id,
      rawType: '', nodeType: '',
      relation: null, relationRef: null, index: null, alias: null,
      spec: null,          // 'CTE' | 'InitPlan' | 'SubPlan' for section headers
      specName: null,
      parent: null, children: [],
      depth: 0, indent: 0,
      head: '', lines: [],  // attribute/detail lines (without head)
      // planner estimates
      costStartup: null, costTotal: null, planRows: null, planWidth: null,
      // actuals
      timeStartup: null, timeTotal: null, rows: null, loops: null,
      never: false,
      // attributes
      buf: {}, ioRead: 0, ioWrite: 0,
      rowsRemoved: 0, rowsRemovedBy: {},
      filters: [],
      workers: null,       // [{num, timeTotal, rows, loops, buf, ...}] from "Worker N:" blocks
      workersPlanned: null, workersLaunched: null,
      heapFetches: null, sortMethod: null,
      // derived (analyze)
      timeIncl: null, timeExcl: null, parallelTime: null,
      gatherWorkers: null,
      rowsTotal: 0, rowsRemovedTotal: 0,
      bufExcl: {}, ioReadExcl: 0, ioWriteExcl: 0,
      ratio: null, ratioDir: 0,
    };
  }

  function parseText(text) {
    const rawLines = text.split('\n');
    const nodes = [];
    const ext = [];
    const triggers = [];
    const diagnostics = [];
    let truncated = false;
    let query = null;

    // aggregate diagnostics by (code, message); keep a few sample fragments
    function addDiag(code, severity, message, sample) {
      let d = diagnostics.find(x => x.code === code && x.message === message);
      if (!d) {
        d = { code, severity, message, count: 0, samples: [] };
        diagnostics.push(d);
      }
      d.count++;
      if (sample != null && d.samples.length < 3) d.samples.push(String(sample).slice(0, 200));
    }

    // pre-scan: strip psql frame (QUERY PLAN header, dashes, "(N rows)")
    const lines = [];
    for (let raw of rawLines) {
      // psql wrapped-line continuation marker / CSV artifacts at line end.
      // trimEnd, not a /[ \t]+$/ replace: an end-anchored regex backtracks
      // from every position of the long leading-space runs of deep plans,
      // turning parse time quadratic in the line length
      let line = raw.trimEnd();
      if (!line.trim()) continue;
      const t = line.trim();
      if (t === 'QUERY PLAN' || /^-{3,}$/.test(t) || /^\(\d+ rows?\)$/.test(t)) continue;
      // "| plan line |" psql border
      const bm = /^\s*\|(.*)\|\s*$/.exec(line);
      if (bm && bm[1].trim() && bm[1].length > 2) line = bm[1].trimEnd();
      // trailing "+" of "format=aligned" output
      line = line.replace(/ ?\+$/, '');
      lines.push(line);
    }

    // find base indent of the first node line
    let base = -1;
    const nodeStack = [];   // {node, indent}
    let cur = null;         // node receiving attribute lines
    let inExt = null;       // ext entry receiving sub-lines
    let rootSeen = false;
    let curWorker = null;       // active "Worker N:" block on cur
    let curWorkerIndent = -1;

    for (const line of lines) {
      const indent = line.search(/\S/);
      const body = line.slice(indent);

      // --- extension tail entries (Planning Time, JIT, Settings, ...) ---
      const am = RE_ATTR.exec(body);
      let attrKey = am ? am[1] : null;
      // PG ≤ 11 spells these lowercase in TEXT format ("Execution time:");
      // JSON/YAML always capitalize, so canonicalize for parity
      if (attrKey === 'Planning time') attrKey = 'Planning Time';
      else if (attrKey === 'Execution time') attrKey = 'Execution Time';
      else if (attrKey === 'Total runtime') attrKey = 'Total Runtime';
      if (rootSeen && base >= 0 && indent <= base && attrKey && EXT_HEADS.has(attrKey)) {
        const entry = { key: attrKey, value: am[2] !== undefined ? am[2] : '', lines: [body] };
        if (/^(Planning Time|Execution Time|Total Runtime)$/.test(attrKey)) {
          const tm = /([\d.]+) ms/.exec(am[2] || '');
          if (tm) entry.time = Number(tm[1]);
        }
        ext.push(entry);
        inExt = entry;
        cur = null; curWorker = null;
        continue;
      }
      const trg = RE_TRIGGER.exec(body);
      if (trg && base >= 0 && indent <= base) {
        triggers.push({ name: trg[1], time: Number(trg[2]), calls: Number(trg[3]), line: body });
        inExt = null; cur = null; curWorker = null;
        continue;
      }
      if (inExt && indent > base) {
        inExt.lines.push(' '.repeat(Math.max(0, indent - base)) + body);
        // planning block may carry buffers — record io/buffers for display only
        continue;
      }
      inExt = null;

      // --- node lines ---
      const isArrow = body.startsWith('-> ');
      const content = isArrow ? body.replace(/^->\s+/, '') : body;

      if (!rootSeen) {
        // first meaningful line is the root node
        base = indent;
        rootSeen = true;
        if (isArrow) {
          // the plan's own root can never carry an arrow: ancestors were cut
          truncated = true;
          addDiag('truncated_input', 'warn',
            'Plan starts with a child arrow: ancestor node(s) are missing; only node-local recommendations are produced', body);
        }
        const node = makeNode(nodes.length);
        node.indent = indent;
        parseHeadLine(node, content);
        nodes.push(node);
        nodeStack.length = 0;
        nodeStack.push(node);
        cur = node; curWorker = null;
        continue;
      }

      if (isArrow) {
        const node = makeNode(nodes.length);
        node.indent = indent;
        parseHeadLine(node, content);
        attachNode(node);
        nodes.push(node);
        cur = node; curWorker = null;
        continue;
      }

      // spec headers: "CTE name" / "InitPlan 1 (returns $0)" / "SubPlan 1"
      const sm = RE_SPEC.exec(content);
      if (sm && !/:/.test(content)) {
        const node = makeNode(nodes.length);
        node.indent = indent;
        node.spec = sm[1];
        node.specName = content.slice(sm[1].length).trim() || null;
        node.rawHead = content;
        node.rawType = content;
        node.nodeType = sm[1];
        node.head = content;
        attachNode(node);
        nodes.push(node);
        cur = node; curWorker = null;
        continue;
      }

      // "Worker N:" head — start a per-worker stats block
      const wm = RE_WORKER_HEAD.exec(body);
      if (wm && cur) {
        cur.lines.push(body);
        curWorker = makeWorker(Number(wm[1]));
        curWorkerIndent = indent;
        (cur.workers || (cur.workers = [])).push(curWorker);
        if (wm[2]) applyWorkerLine(curWorker, wm[2]);
        continue;
      }
      // deeper-indented lines inside a worker block belong to that worker,
      // not to the node (node-level numbers already include all workers)
      if (curWorker && cur && indent > curWorkerIndent) {
        cur.lines.push(body);
        applyWorkerLine(curWorker, body);
        continue;
      }
      curWorker = null;

      // attribute or continuation line
      if (cur) {
        cur.lines.push(body);
        if (am) applyAttr(cur, am[1], am[2] !== undefined ? am[2] : '');
      } else {
        addDiag('unknown_line', 'info',
          'Unrecognized line(s) outside any plan node were ignored', body);
      }
    }

    function attachNode(node) {
      // parent = nearest node on stack with smaller indent
      while (nodeStack.length && nodeStack[nodeStack.length - 1].indent >= node.indent) {
        nodeStack.pop();
      }
      const parent = nodeStack.length ? nodeStack[nodeStack.length - 1] : null;
      if (parent) {
        node.parent = parent.id;
        parent.children.push(node.id);
        node.depth = parent.depth + 1;
      }
      nodeStack.push(node);
    }

    function parseHeadLine(node, content) {
      node.rawHead = content;
      let head = content;
      let m;
      if ((m = RE_NEVER.exec(head))) {
        node.never = true;
        node.loops = 0; node.rows = 0;
        node.timeStartup = 0; node.timeTotal = 0;
        head = head.slice(0, m.index) + head.slice(m.index + m[0].length);
      }
      if ((m = RE_CURRENT.exec(head))) {
        node.inProgress = true;
        if (m[1] !== undefined) {
          node.currentTimeStartup = Number(m[1]);
          node.currentTimeTotal = Number(m[2]);
        }
        node.currentRows = Number(m[3]);
        node.currentLoop = Number(m[4]);
        head = head.slice(0, m.index) + head.slice(m.index + m[0].length);
      }
      if ((m = RE_ACTUAL.exec(head))) {
        if (m[1] !== undefined) {
          node.timeStartup = Number(m[1]);
          node.timeTotal = Number(m[2]);
        }
        node.rows = Number(m[3]);
        node.loops = Number(m[4]);
        head = head.slice(0, m.index) + head.slice(m.index + m[0].length);
      }
      if ((m = RE_COST.exec(head))) {
        node.costStartup = Number(m[1]);
        node.costTotal = Number(m[2]);
        node.planRows = Number(m[3]);
        node.planWidth = Number(m[4]);
        head = head.slice(0, m.index) + head.slice(m.index + m[0].length);
      }
      // an in-progress node without completed-loop stats: show the current
      // loop's numbers (loop M is still running)
      if (node.inProgress && node.loops == null) {
        node.partialStats = true; // current-loop numbers only, not final
        node.rows = node.currentRows;
        node.loops = node.currentLoop;
        if (node.currentTimeTotal != null) {
          node.timeStartup = node.currentTimeStartup;
          node.timeTotal = node.currentTimeTotal;
        }
      }
      head = head.replace(/\s+$/, '');
      node.head = head;
      parseNodeHead(head, node);
    }

    // tail truncation: log collectors cut plans mid-line, which shows up as
    // unbalanced parentheses on the last line (e.g. "(cost=0.00..118")
    if (lines.length) {
      const last = lines[lines.length - 1];
      let bal = 0;
      for (const ch of last) {
        if (ch === '(') bal++;
        else if (ch === ')') bal--;
      }
      if (bal !== 0) {
        truncated = true;
        addDiag('truncated_input', 'warn',
          'Input ends mid-line: the plan tail is likely cut off; only node-local recommendations are produced',
          last.trim());
      }
    }

    // structural tail truncation: every join prints two children and every
    // single-input operator prints one, unconditionally (never-executed
    // subtrees included) — a node missing them means the text below it was
    // cut off even though the last line itself is well-formed (real archive
    // case: a 118-node plan ending at a childless Nested Loop Semi Join)
    if (!truncated && nodes.length) {
      const kids = new Array(nodes.length).fill(0);
      for (const n of nodes) {
        if (n.parent != null) kids[n.parent]++;
      }
      const oneInput = new Set(['Sort', 'Incremental Sort', 'Hash',
        'Materialize', 'Memoize', 'Aggregate', 'GroupAggregate',
        'HashAggregate', 'MixedAggregate', 'WindowAgg', 'Unique', 'Limit',
        'LockRows', 'Gather', 'Gather Merge', 'Subquery Scan', 'ProjectSet',
        'Group', 'Bitmap Heap Scan']);
      const cut = [];
      for (const n of nodes) {
        if (n.spec) continue;
        const isJoin = /^Nested Loop\b/.test(n.nodeType)
          || /^(?:Merge|Hash)(?: \w+)* Join\b/.test(n.nodeType);
        if ((isJoin && kids[n.id] < 2) || (oneInput.has(n.nodeType) && kids[n.id] < 1)) {
          cut.push(n.head);
        }
      }
      if (cut.length) {
        truncated = true;
        addDiag('truncated_input', 'warn',
          'Plan nodes are missing their children: the plan tail is likely cut off; only node-local recommendations are produced',
          cut.slice(0, 3));
      }
    }

    return { nodes, ext, triggers, query, diagnostics, truncated };
  }

  /* ------------------------------------------------------------------ *
   * Analyzer
   * ------------------------------------------------------------------ */

  function analyze(plan) {
    const nodes = plan.nodes;
    const diagnostics = plan.diagnostics || (plan.diagnostics = []);
    function addDiag(code, severity, message, nodeIds) {
      let d = diagnostics.find(x => x.code === code && x.message === message);
      if (!d) {
        d = { code, severity, message, count: 0, nodes: [] };
        diagnostics.push(d);
      }
      d.count += nodeIds ? nodeIds.length : 1;
      if (nodeIds) for (const id of nodeIds) if (d.nodes.length < 8) d.nodes.push(id);
    }

    // -- parallel context: nodes under a Gather divide loops by workers+1
    function walkGather(id, workers) {
      const n = nodes[id];
      let w = workers;
      if (/^Gather( Merge)?$/.test(n.rawType) && n.workersLaunched != null) {
        w = n.workersLaunched + 1;
      } else if (workers) {
        n.gatherWorkers = workers;
      }
      for (const c of n.children) walkGather(c, w);
    }
    if (nodes.length) walkGather(0, 0);

    // -- inclusive metrics
    for (const n of nodes) {
      if (n.timeTotal != null && n.loops != null) {
        const w = n.gatherWorkers || 1;
        const effLoops = w > 1 ? Math.ceil(n.loops / w) : n.loops;
        n.timeIncl = round3(n.timeTotal * effLoops);
        if (w > 1) n.parallelTime = round3(n.timeTotal * n.loops);
      }
      n.rowsTotal = n.rows != null && n.loops ? Math.round(n.rows * n.loops) : 0;
      n.rowsRemovedTotal = n.rowsRemoved && n.loops ? Math.round(n.rowsRemoved * n.loops) : 0;
    }

    // -- parallel attribution is a heuristic; say so, and validate it against
    // per-worker stats when "Worker N:" blocks are available
    {
      const approx = [];
      const partialWorkers = [];
      const exceed = [];
      for (const n of nodes) {
        if (n.gatherWorkers > 1 && n.timeIncl != null) approx.push(n.id);
        if (!n.workers || !n.workers.length) continue;
        const wt = n.workers.map(w => w.timeTotal).filter(v => v != null);
        if (wt.length) {
          const maxW = Math.max.apply(null, wt);
          const minW = Math.min.apply(null, wt);
          n.workerSkew = maxW > 0 ? round3((maxW - minW) / maxW) : 0;
          if (n.timeIncl != null && maxW > n.timeIncl * 1.25 + 1) exceed.push(n.id);
        }
        const expected = (n.gatherWorkers || 1) - 1;
        if (expected > 0 && n.workers.length < expected) partialWorkers.push(n.id);
      }
      if (approx.length) {
        addDiag('parallel_estimate', 'info',
          'Wall-clock time for nodes under Gather is approximated as time × loops/(workers+1)', approx);
      }
      if (exceed.length) {
        addDiag('parallel_estimate', 'warn',
          'Reported per-worker time exceeds the attributed wall-clock time on some nodes: the parallel approximation underestimates them', exceed);
      }
      if (partialWorkers.length) {
        addDiag('partial_worker_stats', 'warn',
          'Per-worker statistics cover fewer workers than were launched', partialWorkers);
      }
    }

    // spec section headers inherit inclusive metrics of their child subtree
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (!n.spec) continue;
      let ti = 0, has = false;
      const buf = {};
      let ior = 0, iow = 0;
      for (const c of n.children) {
        const ch = nodes[c];
        if (ch.timeIncl != null) { ti += ch.timeIncl; has = true; }
        for (const k of BUFFER_COLS) if (ch.buf[k]) buf[k] = (buf[k] || 0) + ch.buf[k];
        ior += ch.ioRead || 0; iow += ch.ioWrite || 0;
      }
      if (has) n.timeIncl = round3(ti);
      n.buf = buf;
      n.ioRead = round3(ior); n.ioWrite = round3(iow);
    }

    // -- charge spec sections to the node that actually executes them --
    // A CTE runs lazily inside the first CTE Scan that reads it; an
    // InitPlan / SubPlan runs inside the node whose expression references
    // it ($N / (InitPlan N)... / (SubPlan N)). That node's inclusive
    // time/buffers already contain the section, so exclusive metrics must
    // subtract the section there — not at its syntactic parent.
    const isDescendantOf = (id, ancestor) => {
      for (let p = nodes[id].parent; p != null; p = nodes[p].parent) {
        if (p === ancestor) return true;
      }
      return false;
    };
    const chargeInferred = [];
    const chargeFallback = [];
    const bareFallback = [];
    for (const spec of nodes) {
      if (!spec.spec) continue;
      spec.chargedTo = spec.parent; // default: syntactic parent
      if (spec.timeIncl == null) continue;

      if (spec.spec === 'CTE') {
        const name = unquote(spec.specName || '');
        // All scans of this CTE outside its own subtree. The one that pays
        // for the CTE's execution is the one whose actual time can absorb
        // it (lazy execution happens inside the scan that demands rows
        // first) — document order is only a tie-break, not evidence.
        const scans = nodes.filter(n =>
          (n.nodeType === 'CTE Scan' || n.nodeType === 'WorkTable Scan')
          && n.relation === name && n.loops && !isDescendantOf(n.id, spec.id));
        let target = null;
        if (scans.length === 1) {
          target = scans[0];
        } else if (scans.length > 1) {
          const dev = Math.max(0.002, spec.timeIncl * 0.02);
          const covering = scans.filter(n =>
            n.timeIncl != null && n.timeIncl >= spec.timeIncl - dev);
          target = covering.length
            ? covering.reduce((a, b) => (a.timeIncl <= b.timeIncl ? a : b))
            : scans.reduce((a, b) => ((a.timeIncl || 0) >= (b.timeIncl || 0) ? a : b));
        }
        if (target) {
          spec.chargedTo = target.id;
          if (target.id !== spec.parent) chargeInferred.push(spec.id);
        } else {
          chargeFallback.push(spec.id);
        }
        continue;
      }

      // marker tokens referencing this InitPlan / SubPlan
      const markers = [];
      const specHead = spec.rawType; // full header, e.g. "InitPlan 1 (returns $0)"
      const nm = /(InitPlan|SubPlan)\s*(\d*)/.exec(specHead);
      if (nm) markers.push('(' + nm[1] + (nm[2] ? ' ' + nm[2] : '') + ')');
      for (const p of specHead.matchAll(/\$\d+/g)) markers.push(p[0]);
      const dev = Math.max(0.002, spec.timeIncl * 0.02);
      let pick = null;
      if (markers.length) {
        const refRe = new RegExp(markers
          .map(m => m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
          .map(m => (m.startsWith('\\$') ? m + '(?![\\d])' : m))
          .join('|'));
        const candidates = nodes.filter(n =>
          !n.spec && n.id !== spec.id && n.timeIncl != null && n.loops
          && !isDescendantOf(n.id, spec.id)
          && (refRe.test(n.lines.join('\n')) || refRe.test(n.head)));
        if (candidates.length) {
          // tightest fit that still covers the section's time
          const covering = candidates.filter(n => n.timeIncl >= spec.timeIncl - dev);
          pick = (covering.length ? covering : candidates)
            .reduce((a, b) => (a.timeIncl <= b.timeIncl ? a : b));
        }
      }
      if (!pick) {
        chargeFallback.push(spec.id);
        // headers from mangled sources lose "(returns $N)", so the marker
        // search cannot succeed — remember these for the overload pass below
        if (spec.timeIncl > 0.05 && !/\$\d/.test(specHead)) bareFallback.push(spec);
        continue;
      }
      spec.chargedTo = pick.id;
      if (pick.id !== spec.parent) chargeInferred.push(spec.id);
    }

    const chargedBy = new Map(); // nodeId -> [spec nodes charged to it]
    for (const n of nodes) {
      if (n.spec && n.chargedTo != null && n.chargedTo !== n.parent) {
        if (!chargedBy.has(n.chargedTo)) chargedBy.set(n.chargedTo, []);
        chargedBy.get(n.chargedTo).push(n);
      }
    }

    // -- overload re-attribution: a section left on its syntactic parent is
    // usually right (a target-list SubPlan executes inside the owning node),
    // so re-charge a bare-header section elsewhere ONLY when the parent
    // provably cannot contain it — its children plus charged sections sum to
    // more than its own inclusive time (real archive case: four bare
    // InitPlans stayed on a root they did not fit into, +70% Σ self). The
    // new target is the tightest covering main-tree node in the parent's
    // subtree; bodies of other spec sections mirror the section's time
    // exactly and would create a circular charge, so they are excluded.
    if (bareFallback.length) {
      const insideSpec = (id) => {
        for (let p = nodes[id].parent; p != null; p = nodes[p].parent) {
          if (nodes[p].spec) return true;
        }
        return false;
      };
      const loadOf = (n) => {
        let sum = 0;
        for (const c of n.children) {
          const ch = nodes[c];
          if (ch.spec && ch.chargedTo != null && ch.chargedTo !== n.id) continue;
          if (ch.timeIncl != null) sum += ch.timeIncl;
        }
        for (const s of chargedBy.get(n.id) || []) sum += s.timeIncl || 0;
        return sum;
      };
      bareFallback.sort((a, b) => b.timeIncl - a.timeIncl);
      for (const spec of bareFallback) {
        const parent = spec.parent != null ? nodes[spec.parent] : null;
        if (!parent || parent.timeIncl == null) continue;
        if (loadOf(parent) <= parent.timeIncl + Math.max(0.05, parent.timeIncl * 0.001)) continue;
        const dev = Math.max(0.002, spec.timeIncl * 0.02);
        const scope = nodes.filter(n =>
          !n.spec && n.id !== spec.id && n.id !== parent.id
          && n.timeIncl != null && n.loops
          && !insideSpec(n.id) && isDescendantOf(n.id, parent.id)
          && n.timeIncl >= spec.timeIncl - dev);
        if (!scope.length) continue;
        const pick = scope.reduce((a, b) => (a.timeIncl <= b.timeIncl ? a : b));
        spec.chargedTo = pick.id;
        if (!chargedBy.has(pick.id)) chargedBy.set(pick.id, []);
        chargedBy.get(pick.id).push(spec);
        chargeInferred.push(spec.id);
        const fi = chargeFallback.indexOf(spec.id);
        if (fi >= 0) chargeFallback.splice(fi, 1);
      }
    }

    if (chargeInferred.length) {
      addDiag('charge_inferred', 'info',
        'CTE/InitPlan/SubPlan time was attributed to the node that appears to execute it (heuristic)', chargeInferred);
    }
    if (chargeFallback.length) {
      addDiag('charge_fallback', 'info',
        'The executing node of some CTE/InitPlan/SubPlan sections was not found: their time stays on the syntactic parent', chargeFallback);
    }
    // -- monotonic repair: per-loop actual times are printed with 1 µs
    // resolution, so at millions of loops a parent can print less inclusive
    // time than its own children accumulate beneath it (real archive case:
    // Memoize at 21.8M loops prints "0.000" while its Index Scan child
    // holds 5.8 s — which then double-counts into Σ self). When the deficit
    // is explainable by that rounding, raise the parent to the children's
    // sum bottom-up before subtracting. Deficits beyond the rounding budget
    // are left alone — they are diagnosed as excl_overshoot / clamped.
    const inclRaised = [];
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.spec || n.timeIncl == null || n.loops == null) continue;
      let sum = 0, loopsBudget = n.loops;
      for (const c of n.children) {
        const ch = nodes[c];
        if (ch.spec && ch.chargedTo != null && ch.chargedTo !== n.id) continue;
        if (ch.timeIncl != null) { sum += ch.timeIncl; loopsBudget += ch.loops || 0; }
      }
      for (const s of chargedBy.get(n.id) || []) {
        if (s.timeIncl != null) { sum += s.timeIncl; loopsBudget += s.loops || 0; }
      }
      const deficit = round3(sum - n.timeIncl);
      if (deficit > 0.005 && deficit <= 0.0005 * loopsBudget + 0.05) {
        n.inclRaised = deficit;
        n.timeIncl = round3(sum);
        inclRaised.push(n.id);
      }
    }
    if (inclRaised.length) {
      addDiag('metric_raised', 'info',
        'Inclusive time of some nodes was raised to the sum of their children: '
        + 'per-loop actual times are printed with 1 µs resolution and lose '
        + 'precision at high loop counts', inclRaised);
    }

    const clamped = [];
    for (const n of nodes) {
      let childTime = 0, hasChildTime = false;
      const childBuf = {};
      let childIoR = 0, childIoW = 0;
      const subtractors = [];
      for (const c of n.children) {
        const ch = nodes[c];
        if (ch.spec && ch.chargedTo != null && ch.chargedTo !== n.id) continue;
        subtractors.push(ch);
      }
      for (const s of chargedBy.get(n.id) || []) subtractors.push(s);
      for (const ch of subtractors) {
        if (ch.timeIncl != null) { childTime += ch.timeIncl; hasChildTime = true; }
        for (const k of BUFFER_COLS) if (ch.buf[k]) childBuf[k] = (childBuf[k] || 0) + ch.buf[k];
        childIoR += ch.ioRead || 0;
        childIoW += ch.ioWrite || 0;
      }
      if (n.timeIncl != null) {
        const raw = round3(n.timeIncl - childTime);
        n.timeExcl = Math.max(0, raw);
        if (raw < -0.01) { n.exclClamped = -raw; clamped.push(n.id); }
      } else if (hasChildTime) {
        n.timeExcl = null;
      }
      for (const k of BUFFER_COLS) {
        const v = (n.buf[k] || 0) - (childBuf[k] || 0);
        if (v > 0) n.bufExcl[k] = v;
      }
      n.ioReadExcl = round3(Math.max(0, (n.ioRead || 0) - childIoR));
      n.ioWriteExcl = round3(Math.max(0, (n.ioWrite || 0) - childIoW));
    }
    if (clamped.length) {
      addDiag('metric_clamped', 'info',
        'Negative exclusive time was clamped to zero (attribution/rounding artifact)', clamped);
    }

    // -- exclusive cost (PG costs are inclusive of children) --
    for (const n of nodes) {
      if (n.costTotal == null) continue;
      let childCost = 0;
      for (const c of n.children) {
        const ch = nodes[c];
        const cc = ch.costTotal != null ? ch.costTotal
          : ch.spec ? ch.children.reduce((s, g) => s + (nodes[g].costTotal || 0), 0) : 0;
        childCost += cc;
      }
      n.costExcl = Math.round(Math.max(0, n.costTotal - childCost) * 100) / 100;
    }

    // -- planned vs actual rows ratio
    for (const n of nodes) {
      if (n.planRows == null || n.rows == null || n.spec || n.never
          || n.partialStats) continue; // in-progress rows are not final
      const act = n.rows, est = n.planRows;
      if (act === 0 || est === 0) {
        if (act !== est) { n.ratio = Infinity; n.ratioDir = act > est ? 1 : -1; }
        continue;
      }
      const r = act > est ? act / est : est / act;
      if (r < 1.05) continue; // close enough to call it a hit
      n.ratio = r;
      n.ratioDir = act > est ? 1 : -1;
    }

    // -- maxima + totals
    const max = {
      timeExcl: 0, timeIncl: 0, rows: 0, rowsRemoved: 0, loops: 0, ratio: 0,
      ioRead: 0, ioWrite: 0, buf: {}, costExcl: 0, planRows: 0,
    };
    const totals = {
      rowsRemoved: 0, ioRead: 0, ioWrite: 0, buf: {},
      bufReadBytes: 0, bufHitBytes: 0,
    };
    let anyFilter = false, anyLoops = false, anyNever = false, anyRatio = false;

    for (const n of nodes) {
      if (n.spec) continue;
      if (n.timeExcl != null) max.timeExcl = Math.max(max.timeExcl, n.timeExcl);
      if (n.timeIncl != null) max.timeIncl = Math.max(max.timeIncl, n.timeIncl);
      max.rows = Math.max(max.rows, n.rowsTotal);
      max.rowsRemoved = Math.max(max.rowsRemoved, n.rowsRemovedTotal);
      if (n.loops != null) max.loops = Math.max(max.loops, n.loops);
      if (n.ratio != null && n.ratio !== Infinity) max.ratio = Math.max(max.ratio, n.ratio);
      if (n.costExcl != null) max.costExcl = Math.max(max.costExcl, n.costExcl);
      if (n.planRows != null) max.planRows = Math.max(max.planRows, n.planRows);
      max.ioRead = Math.max(max.ioRead, n.ioReadExcl);
      max.ioWrite = Math.max(max.ioWrite, n.ioWriteExcl);
      for (const k of BUFFER_COLS) {
        if (n.bufExcl[k]) {
          max.buf[k] = Math.max(max.buf[k] || 0, n.bufExcl[k]);
          totals.buf[k] = (totals.buf[k] || 0) + n.bufExcl[k];
        }
      }
      totals.rowsRemoved += n.rowsRemovedTotal;
      totals.ioRead = round3(totals.ioRead + n.ioReadExcl);
      totals.ioWrite = round3(totals.ioWrite + n.ioWriteExcl);
      if (n.filters.length) anyFilter = true;
      if (n.loops != null && n.loops > 1) anyLoops = true;
      if (n.never) anyNever = true;
      if (n.ratio != null) anyRatio = true;
    }

    const rootNode = nodes[0] || null;
    totals.time = rootNode && rootNode.timeIncl != null ? rootNode.timeIncl : null;
    totals.rows = rootNode ? rootNode.rowsTotal : 0;

    let planningTime = null, executionTime = null;
    for (const e of plan.ext) {
      if (e.key === 'Planning Time') planningTime = e.time != null ? e.time : planningTime;
      if (e.key === 'Execution Time' || e.key === 'Total Runtime') {
        executionTime = e.time != null ? e.time : executionTime;
      }
    }

    // JIT tail block: compilation is charged to execution time but belongs to
    // no plan node, so it stays invisible in the tree — structure it here.
    //   Functions: 109
    //   Options: Inlining true, Optimization true, ...
    //   Timing: Generation 11.723 ms, ..., Total 2851.190 ms
    plan.jit = null;
    for (const e of plan.ext) {
      if (e.key !== 'JIT') continue;
      const jit = { functions: null, options: {}, timing: {}, total: null };
      for (const l of e.lines) {
        const fm = /^\s*Functions:\s*(\d+)/.exec(l);
        if (fm) { jit.functions = Number(fm[1]); continue; }
        const om = /^\s*Options:\s*(.*)$/.exec(l);
        if (om) {
          for (const part of om[1].split(',')) {
            const p = /^\s*([A-Za-z][A-Za-z ]*?)\s+(true|false)\s*$/.exec(part);
            if (p) jit.options[p[1].trim().toLowerCase()] = p[2] === 'true';
          }
          continue;
        }
        const tm = /^\s*Timing:\s*(.*)$/.exec(l);
        if (tm) {
          for (const part of tm[1].split(',')) {
            const p = /^\s*([A-Za-z][A-Za-z ]*?)\s+([\d.]+)\s*ms\s*$/.exec(part);
            if (p) jit.timing[p[1].trim().toLowerCase()] = Number(p[2]);
          }
        }
      }
      if (jit.timing.total != null) jit.total = jit.timing.total;
      else {
        const parts = Object.values(jit.timing);
        if (parts.length) jit.total = round3(parts.reduce((s, v) => s + v, 0));
      }
      plan.jit = jit;
      break;
    }

    // the ceil(loops/workers) wall-clock model rounds up per node, so on
    // parallel plans sibling self times can add up to more than the root —
    // say so instead of letting the numbers quietly disagree
    if (totals.time != null && totals.time > 0) {
      let sumExcl = 0;
      let hasExcl = false;
      for (const n of nodes) {
        if (!n.spec && n.timeExcl != null) { sumExcl += n.timeExcl; hasExcl = true; }
      }
      if (hasExcl && sumExcl > totals.time * 1.02 + 0.1) {
        // name the mechanism that actually produced the overshoot instead of
        // blaming parallelism on plans that have none
        const seen = c => diagnostics.some(d => d.code === c);
        const parallel = nodes.some(n => n.gatherWorkers > 0 || n.workersLaunched > 0);
        const cause = plan.truncated
          ? 'the plan is cut off: nodes whose children are missing carry the whole subtree '
            + 'time as their own'
          : parallel
          ? 'the ceil(loops / workers) wall-clock model rounds up on every parallel node'
          : seen('metric_raised')
            ? 'per-loop times are printed with 1 µs resolution, and at high loop counts the '
              + 'rounding adds up to whole seconds'
            : seen('charge_fallback') || seen('charge_inferred')
              ? 'the executing node of some CTE/InitPlan/SubPlan sections could not be identified, '
                + 'so their time is counted where the section is written'
              : 'rounding and attribution artifacts accumulate across the tree';
        addDiag('excl_overshoot', 'warn',
          'Sum of node self times exceeds the root wall-clock time by '
          + Math.round((sumExcl / totals.time - 1) * 100)
          + '%: ' + cause + ' — treat per-node self times as upper bounds');
      }
    }

    // -- what qualifies the reading of this plan, beyond model artifacts
    if (nodes.length && !plan.truncated) {
      const hasRuntime = nodes.some(n => n.loops != null || n.never);
      if (hasRuntime && executionTime == null && planningTime == null) {
        addDiag('totals_missing', 'info',
          'The plan carries no Planning Time / Execution Time line: time spent outside the '
          + 'tree (planning, JIT, result transfer, triggers) cannot be accounted for');
      }
      const neverIds = nodes.filter(n => n.never && !n.spec).map(n => n.id);
      if (neverIds.length) {
        addDiag('never_executed', 'info',
          neverIds.length + ' node(s) were never executed: nothing reached them — an outer side '
          + 'returned no rows, a one-time filter was false, a LIMIT stopped execution, or a '
          + 'partition was pruned at run time. They carry no timing and no recommendations',
          neverIds);
      }
      let pruned = 0;
      for (const n of nodes) if (n.subplansRemoved > 0) pruned += n.subplansRemoved;
      if (pruned) {
        addDiag('runtime_pruning', 'info',
          pruned + ' partition subplan(s) were removed at run time: the plan shows only the '
          + 'partitions that survived pruning, not the ones the query could have touched');
      }
    }

    // -- external parameters vs InitPlan/SubPlan outputs. Both print as "$N",
    // but only an external one means the plan was built without knowing the
    // value, which changes what a bad row estimate means.
    {
      const internal = new Set();
      for (const n of nodes) {
        if (!n.spec) continue;
        for (const m of String(n.rawType || '').matchAll(/\$(\d+)/g)) internal.add(m[1]);
      }
      const external = new Set();
      for (const n of nodes) {
        if (n.spec) continue;
        for (const f of n.filters) {
          // a "$1" inside a string literal is data, not a parameter
          const bare = String(f.val || '').replace(/'(?:[^']|'')*'/g, "''");
          for (const m of bare.matchAll(/\$(\d+)/g)) {
            if (!internal.has(m[1])) external.add(m[1]);
          }
        }
      }
      const asc = (a, b) => Number(a) - Number(b);
      plan.parameters = {
        external: [...external].sort(asc).map(x => '$' + x),
        internal: [...internal].sort(asc).map(x => '$' + x),
      };
    }

    plan.max = max;
    plan.totals = totals;
    plan.planningTime = planningTime;
    plan.executionTime = executionTime;
    const hasTime = max.timeExcl > 0 || max.timeIncl > 0;
    plan.columns = {
      time: hasTime,
      // cost-only plans (EXPLAIN without ANALYZE): show planner numbers instead
      cost: !hasTime && max.costExcl > 0,
      estRows: !hasTime && max.planRows > 0,
      ioRead: max.ioRead > 0,
      ioWrite: max.ioWrite > 0,
      rows: max.rows > 0,
      ratio: anyRatio,
      rowsRemoved: max.rowsRemoved > 0,
      filter: anyFilter,
      loops: anyLoops || anyNever,
      buf: BUFFER_COLS.filter(k => max.buf[k] > 0),
    };
    return plan;
  }

  /* ------------------------------------------------------------------ *
   * Stats: aggregate nodes by (type, relation, index)
   * ------------------------------------------------------------------ */

  function buildStats(plan) {
    const groups = new Map();
    let totalTime = 0;
    for (const n of plan.nodes) {
      if (n.spec || n.loops === 0 || n.never) continue;
      const key = n.rawType + '\u0000' + (n.relation || '') + '\u0000' + (n.index || '');
      let g = groups.get(key);
      if (!g) {
        g = {
          rawType: n.rawType, nodeType: n.nodeType, relation: n.relation, index: n.index,
          time: 0, ioRead: 0, ioWrite: 0, rows: 0, rowsRemoved: 0, loops: 0,
          buf: {}, ids: [],
        };
        groups.set(key, g);
      }
      g.ids.push(n.id);
      if (n.timeExcl != null) { g.time = round3(g.time + n.timeExcl); totalTime += n.timeExcl; }
      g.ioRead = round3(g.ioRead + n.ioReadExcl);
      g.ioWrite = round3(g.ioWrite + n.ioWriteExcl);
      g.rows += n.rowsTotal;
      g.rowsRemoved += n.rowsRemovedTotal;
      g.loops += n.loops || 0;
      for (const k of BUFFER_COLS) if (n.bufExcl[k]) g.buf[k] = (g.buf[k] || 0) + n.bufExcl[k];
    }
    const list = [...groups.values()];
    for (const g of list) g.timePct = totalTime > 0 ? g.time / totalTime * 100 : null;
    list.sort((a, b) => b.time - a.time || b.rows - a.rows);
    plan.stats = list;
  }

  /* ------------------------------------------------------------------ *
   * Domain: collapse the plan to its structural skeleton
   * (joins + data sources, everything else lifted through)
   * ------------------------------------------------------------------ */

  const SCAN_KIND = [
    [/^Function Scan|^Table Function Scan/, 'Function'],
    [/^Values Scan/, 'Values'],
    [/^CTE Scan|^WorkTable Scan/, 'CTE'],
    [/Foreign Scan$/, 'Table Foreign'],
    [/^Subquery Scan/, 'Subquery'],
    [/^Sample Scan/, 'Table Sample'],
    [/Scan/, 'Table'],
  ];

  function buildDomain(plan) {
    const nodes = plan.nodes;

    function collect(id) {
      const n = nodes[id];
      const childEntries = [];
      for (const c of n.children) childEntries.push(...collect(c));

      if (!n.spec) {
        if (/^(Insert|Update|Delete|Merge)$/.test(n.nodeType)) {
          return [{ label: n.nodeType + (n.relation ? ' ' + n.relation : ''), children: childEntries }];
        }
        if (/Join$|^Nested Loop/.test(n.nodeType)) {
          // merge nested joins into one
          const merged = [];
          for (const e of childEntries) {
            if (e.label === 'Join') merged.push(...e.children);
            else merged.push(e);
          }
          return [{ label: 'Join', children: merged }];
        }
        if (n.relation != null && /Scan/.test(n.nodeType) && n.nodeType !== 'Bitmap Index Scan') {
          const kind = (SCAN_KIND.find(([re]) => re.test(n.nodeType)) || [null, 'Table'])[1];
          if (n.nodeType.startsWith('Subquery Scan')) {
            return [{ label: 'Subquery ' + n.relation, children: childEntries }];
          }
          return [{ label: 'Scan ' + kind + ' ' + n.relation, children: [] }];
        }
      }
      return childEntries; // lift through process/spec nodes
    }

    const lines = [];
    const seen = new Set();
    function emit(entry, depth) {
      const line = (depth ? '  '.repeat(depth) + '->  ' : '') + entry.label;
      const key = depth + '|' + entry.label;
      if (!entry.children.length && seen.has(key)) return; // dedupe repeated leaves
      seen.add(key);
      lines.push(line);
      for (const ch of entry.children) emit(ch, depth + 1);
    }
    const roots = plan.nodes.length ? collect(0) : [];
    for (const r of roots) emit(r, 0);
    plan.domain = lines;
  }

  /* ------------------------------------------------------------------ *
   * Advisor — heuristic recommendations.
   * ------------------------------------------------------------------ */

  // Advice metadata, schema v2: every rule separates what the plan shows
  // (obs — facts only) from what it might mean (hyp — explicitly hedged)
  // and an optional safe next step (next). High-impact DBA actions are
  // never presented as certain when a plan cannot prove them.
  const SET_LOCAL_NOTE = 'Test with more memory scoped to one session: '
    + "BEGIN; SET LOCAL work_mem = '<observed spill + headroom>'; ... COMMIT; "
    + 'a global work_mem increase multiplies memory use across every concurrent backend.';

  // PostgreSQL prints spill sizes in kB; show them the way a human reads them
  const trimZero = v => v.toFixed(1).replace(/\.0$/, '');
  const fmtKb = kb => {
    if (kb == null) return null;
    if (kb >= 1024 * 1024) return trimZero(kb / 1048576) + ' GB';
    if (kb >= 1024) return trimZero(kb / 1024) + ' MB';
    return kb + ' kB';
  };
  // A spill of N kB needs somewhat more than N of work_mem: the in-memory
  // representation carries per-tuple overhead the spill file does not.
  const MEM_LADDER = [4, 8, 16, 32, 64, 128, 256, 512, 1024];   // MB
  const workMemFor = kb => {
    const needMb = kb * 1.4 / 1024;
    for (const m of MEM_LADDER) if (m >= needMb) return m === 1024 ? '1GB' : m + 'MB';
    return null;                     // past any sane per-node, per-backend budget
  };
  // concrete, size-aware replacement for SET_LOCAL_NOTE
  const memNote = kb => {
    if (!kb) return SET_LOCAL_NOTE;
    const w = workMemFor(kb);
    if (w) {
      return 'Test it in one session first: BEGIN; SET LOCAL work_mem = \'' + w + "'; <query> COMMIT; "
        + '— work_mem is granted per sort/hash node per backend, so a global increase '
        + 'multiplies memory use across every concurrent query.';
    }
    return 'The spill is ' + fmtKb(kb) + ': sizing work_mem for it is not realistic. '
      + 'Reduce the row set before this node (filter or pre-aggregate earlier), or give the '
      + 'planner an ordered/indexed path that removes the sort or hash altogether.';
  };
  const ADVICE_META = {
    BITMAP_AND:  { sev: 'idx',
      obs: 'Several bitmap index scans on the same table are intersected (BitmapAnd) to satisfy these conditions.',
      hyp: 'One composite index covering all the conditions could serve this scan directly.' },
    BITMAP_OR:   { sev: 'idx',
      obs: 'Several bitmap index scans are combined with OR.',
      hyp: 'If this node is material, rewriting as a UNION ALL of per-condition queries sometimes uses the indexes more efficiently.' },
    BITMAP_LOSSY:{ sev: 'mem',
      obs: 'The bitmap did not fit into work_mem and became lossy: whole heap pages are re-checked row by row.',
      next: SET_LOCAL_NOTE },
    DISK_SORT: { sev: 'mem',
      obs: 'The sort did not fit into work_mem and spilled to disk.',
      hyp: 'An index providing the required order would avoid the sort entirely; more memory would keep it off disk.',
      next: SET_LOCAL_NOTE },
    DISK_HASH: { sev: 'mem',
      obs: 'The hash table did not fit into work_mem: it was split into batches written to temp files.',
      hyp: 'Every extra batch means the probe side is written out and read back once more.',
      next: SET_LOCAL_NOTE },
    MEMOIZE_MISS:{ sev: 'mem',
      obs: 'The Memoize cache is not paying for itself: most lookups miss.',
      hyp: 'Either the cache is too small for the key space (entries are evicted before they are reused), '
        + 'or the parameter values barely repeat, so caching only adds overhead.',
      next: 'Check the Cache Key cardinality against the loop count; if evictions dominate, more work_mem '
        + '(hash_mem_multiplier) can help — if hits stay near zero, the plan is better off without the Memoize.' },
    SQL_NOTIN: { sev: 'warn',
      obs: 'The query uses NOT IN (SELECT ...), and the plan evaluates it as a subplan per row '
        + 'instead of as an anti-join.',
      hyp: 'NOT IN can never become an anti-join, because NULL makes it three-valued on both '
        + 'sides: one NULL in the subquery makes the predicate never true, and a NULL on the '
        + 'left is dropped as well. PostgreSQL therefore keeps a (hashed) subplan.',
      next: 'NOT EXISTS would let the planner use an anti-join, but it is not a drop-in '
        + 'replacement — it keeps rows that NOT IN discards. Rewrite only after establishing '
        + 'that both the compared column and the subquery column are NOT NULL, or carry the '
        + 'difference explicitly in the predicate.' },
    SQL_CAST: { sev: 'idx',
      obs: 'The query casts a column in this predicate, so the comparison happens on the cast '
        + 'value rather than on the column itself.',
      hyp: 'A plain index on the column cannot serve that comparison — PostgreSQL would need an '
        + 'index on exactly this expression. Casting the other side (the parameter or the '
        + 'literal) instead keeps the column indexable.',
      next: 'Check the column type against what it is compared with: if they already match, the '
        + 'cast can go. If the cast is unavoidable, an expression index on the written '
        + 'expression is the alternative.' },
    JIT_TIME: { sev: 'warn',
      obs: 'A large share of the execution time went into JIT compilation rather than into the plan itself.',
      hyp: 'The planner’s cost estimate crossed jit_above_cost, but the query does not run long enough '
        + 'for compiled code to earn the compilation back.',
      next: 'Compare against SET LOCAL jit = off; if compilation keeps dominating, raise jit_above_cost / '
        + 'jit_optimize_above_cost (optimization and inlining are usually the expensive parts).' },
    LIMIT_SORT: { sev: 'hint',
      obs: 'LIMIT returns only a small fraction of the rows that are fetched and sorted below it.',
      hyp: 'An index on the sort keys would deliver rows already ordered, letting the scan stop early.' },
    LIMIT_OFFSET: { sev: 'hint',
      obs: 'LIMIT/OFFSET discards most of the rows read below it.',
      hyp: 'Keyset pagination (WHERE key > last-seen ORDER BY key) avoids re-reading the skipped rows.' },
    INDEX_DISCARD: { sev: 'crit',
      obs: 'Most rows fetched through the index are then discarded by the filter.',
      hyp: 'An index covering the filter conditions would avoid fetching rows only to discard them.' },
    SEQSCAN_DISCARD: { sev: 'crit',
      obs: 'The sequential scan discards most of the rows it reads by filter.',
      hyp: 'An index on the filter conditions could replace the full-table read.' },
    CTE_RESCAN: { sev: 'warn',
      obs: 'The CTE result is re-scanned many times over a large row set.',
      hyp: 'Restructuring the join, or materializing a keyed lookup, could avoid the repeated scans.' },
    INDEX_FULLREAD: { sev: 'hint',
      obs: 'The index is used without any key condition — only for ordered reading or a full traversal.' },
    ROW_ESTIMATE:{ sev: 'info',
      obs: 'The planner’s row estimate differs strongly from the actual count.',
      hyp: 'Statistics may be outdated, or the predicate may be inherently hard to estimate (correlated columns, expressions).',
      next: 'Run ANALYZE on the table; if the estimate stays off, consider extended statistics (CREATE STATISTICS).' },
    SEQSCAN_BUFFERS: { sev: 'io',
      obs: 'The scan reads many buffers per row it returns.',
      hyp: 'This can indicate table bloat — but wide rows or low selectivity produce the same picture; the plan alone cannot tell.',
      next: 'Verify bloat first (pgstattuple, dead tuples in pg_stat_user_tables). VACUUM FULL / pg_repack are heavy, locking operations — only after confirmation.' },
    INDEX_BUFFERS: { sev: 'io',
      obs: 'The scan reads many buffers per row it returns.',
      hyp: 'Possible causes: table or index bloat, or the scan entering the middle of the index — the plan alone cannot tell.',
      next: 'Verify bloat first (pgstattuple, dead tuples in pg_stat_user_tables) before any VACUUM FULL / pg_repack.' },
    TABLE_WRITTEN: { sev: 'io',
      obs: 'Reading this table also wrote shared buffers.',
      hyp: 'Typical causes: hint-bit writes after bulk changes, or checkpoint backlog flushing through this backend.' },
    TEMP_SPILL: { sev: 'mem',
      obs: 'The node wrote temp buffers: its working set did not fit into work_mem.',
      next: SET_LOCAL_NOTE },
    DISK_READ: { sev: 'io',
      obs: 'Node self time is dominated by disk reads, as reported by the plan’s own I/O Timings.',
      hyp: 'Cold cache or slow storage: the average time per read is far above a warm-cache access.',
      next: 'Re-run to compare against a warm cache; if it stays slow, look at storage latency and the shared_buffers hit ratio for this relation.' },
    UNEXPLAINED_TIME: { sev: 'warn',
      obs: 'Node self time is far larger than its buffer traffic and measured I/O can explain.',
      hyp: 'The plan alone cannot tell why: CPU-heavy expressions, lock waits, or a saturated host all look like this.',
      next: 'Correlate with pg_stat_activity / wait events while the query runs.' },
    NESTLOOP_DISCARD: { sev: 'crit',
      obs: 'The nested-loop join filter discards almost every row pairing it examines: the inner side is scanned in full for the outer rows.',
      hyp: 'An index on the join key would let the loop probe matching rows directly — or let the planner switch to a hash join.' },
    REPEATED_WORK: { sev: 'info',
      obs: 'An identical subtree is executed more than once.',
      hyp: 'Reusing one result (CTE, temp table, or computing the values together) may save the repeated work.' },
    GATHER_WORKERS: { sev: 'info',
      obs: 'Fewer parallel workers were launched than the planner asked for.',
      hyp: 'The worker pool (max_parallel_workers / max_worker_processes) may have been exhausted at that moment.' },
    REDUNDANT_SORT: { sev: 'crit',
      obs: 'Redundant nested sort: the inner sort’s order is discarded by the outer sort.' },
    REDUNDANT_GROUP:{ sev: 'crit',
      obs: 'The same grouping keys are aggregated twice in a row.' },
    JOIN_FULLREAD: { sev: 'crit',
      obs: 'The whole table is read and hashed/merged, but the join keeps only a small fraction of its rows.',
      hyp: 'If the join key is selective, an indexed nested-loop lookup could avoid the full read. A missing index on the join (foreign-key) column is a common cause — but the plan does not show which indexes exist.' },
    ANTIJOIN_FULLREAD: { sev: 'crit',
      obs: 'The anti-join reads the whole table to reject a small fraction of rows.',
      hyp: 'If the join key is selective, an index on it could avoid the full read — the plan does not show which indexes exist.' },
    OUTSIDE_PLAN: { sev: 'mem',
      obs: 'A large share of the total execution time is spent outside the plan tree.',
      hyp: 'Typical causes: result-set transfer to the client, triggers, or serialization.' },
    PLANNING_TIME: { sev: 'warn',
      obs: 'Planning takes a large share of the total latency: the query is cheap to run but expensive to plan.',
      hyp: 'Typical causes: many joined relations or partitions, a large number of indexes to consider, '
        + 'or replanning the same statement on every call.',
      next: 'Reuse the plan (prepared statements; plan_cache_mode = force_generic_plan for stable shapes). '
        + 'If the table is partitioned, check how many partitions survive pruning at plan time.' },
  };

  // rules that name a measured cause for a node's time; UNEXPLAINED_TIME is the
  // residual finding and must stand down where one of these already fired
  const CAUSE_CODES = new Set([
    'DISK_SORT', 'DISK_HASH', 'TEMP_SPILL', 'BITMAP_LOSSY', 'DISK_READ', 'MEMOIZE_MISS',
    'SEQSCAN_DISCARD', 'INDEX_DISCARD', 'NESTLOOP_DISCARD', 'SEQSCAN_BUFFERS', 'INDEX_BUFFERS',
    'JOIN_FULLREAD', 'ANTIJOIN_FULLREAD', 'CTE_RESCAN', 'LIMIT_OFFSET', 'BITMAP_AND',
  ]);

  // findings that need nothing but the node's own lines: still trustworthy
  // when the plan tree arrived incomplete
  const LOCAL_CODES = new Set([
    'DISK_SORT', 'DISK_HASH', 'TEMP_SPILL', 'BITMAP_LOSSY', 'MEMOIZE_MISS',
    'SEQSCAN_DISCARD', 'INDEX_DISCARD', 'ROW_ESTIMATE', 'SEQSCAN_BUFFERS', 'INDEX_BUFFERS',
    'TABLE_WRITTEN', 'DISK_READ', 'GATHER_WORKERS', 'CTE_RESCAN', 'SQL_CAST',
    // INDEX_FULLREAD is deliberately absent: it fires on the *absence* of an
    // "Index Cond:" line, which a cut-off plan cannot distinguish from a
    // line that simply did not arrive
  ]);

  const badgeOf = code => code.replace(/(?:^|_)(.)[^_]*/g, '$1');

  function buildAdvice(plan) {
    // An incomplete tree breaks every relation between a node and its
    // children — parent/child rules, duplicate-subtree detection and the
    // self-time arithmetic all become guesses. Node-local findings (a spill,
    // a filter throwing rows away, a thrashing cache) are still readable off
    // the lines that did arrive, and on a cut multi-minute plan they are the
    // only thing the user has. They are emitted without a share-of-total.
    const localOnly = !!plan.truncated;
    const nodes = plan.nodes;
    let advice = [];
    const real = n => n && !n.spec;
    const firstRealChild = n => {
      for (const c of n.children) if (real(nodes[c])) return nodes[c];
      return null;
    };
    const realChildren = n => n.children.map(c => nodes[c]).filter(real);
    const hasIndexCond = n => n.filters.some(f => f.key === 'Index Cond');
    const rowsX = n => {
      const rr = n.rowsTotal, rf = n.rowsRemovedTotal;
      return rr && rf ? `rows=${rr + rf} (${rr} kept + ${rf} removed by filter)`
        : rf ? `removed by filter=${rf}` : `rows=${rr}`;
    };
    const ratioX = (x, y) => {
      if (!x || !y) return '';
      const r = Math.max(x, y) / Math.min(x, y);
      return ', ratio=' + (r >= 1000 ? (r / 1000).toFixed(1) + 'K' : r.toFixed(1));
    };
    // impactMs (optional) overrides the default per-node time attribution —
    // e.g. TABLE_WRITTEN is about the write cost, not the node's whole self time
    // `over` replaces the static wording where the observed numbers allow a
    // sharper statement (a concrete work_mem value, a measured cause)
    const add = (code, heads, idxSpec, impactMs, over) => {
      if (localOnly && !LOCAL_CODES.has(code)) return;
      const meta = ADVICE_META[code];
      const entry = {
        code, badge: badgeOf(code), sev: meta.sev,
        obs: meta.obs, hyp: meta.hyp || null, next: meta.next || null,
        nodes: heads.map(h => ({ id: h.n.id, ext: h.ext || null })),
      };
      if (over) Object.assign(entry, over);
      if (impactMs != null) entry.impactMs = impactMs;
      if (idxSpec && Expr) {
        try {
          const idxs = Expr.suggestIndexes(idxSpec);
          if (idxs && idxs.length) entry.idxs = idxs;
        } catch (e) { /* suggestion is best-effort */ }
      }
      advice.push(entry);
      for (const h of heads) (h.n.advice ??= []).push(entry);
    };
    // index-suggestion input from a scan node's own conditions
    const sqlCtx = plan.sql && plan.sql.bound ? plan.sql : null;
    // Casts the query wrote for *this* relation, as "col::type". Attribution
    // is per FROM item and includes the type: two tables joined on columns
    // that share a name must not inherit each other's casts.
    const writtenCastsOf = n => (sqlCtx && n.sqlCasts ? new Set(n.sqlCasts) : null);
    const scanSpec = (n, extra) => ({
      relation: n.relationRef || n.relation,
      alias: n.alias,
      // the plan names the index this scan already uses: never propose one
      // that only repeats its key columns
      usesIndex: !!n.index,
      // an empty set still means "the query is known and wrote no cast here"
      writtenCasts: sqlCtx ? (writtenCastsOf(n) || new Set()) : null,
      conds: [
        ...n.filters.map(f => ({ key: f.key, text: f.val })),
        ...(extra || []),
      ],
    });

    // subtree signatures for REPEATED_WORK
    const sigHash = new Map();
    const sigDone = new Set();
    // whether the plan carries buffer counters at all — decides if the
    // "unexplained time" finding can be made per node or only for the plan
    const hasBufData = nodes.some(n => Object.keys(n.buf).length > 0);
    const slowNoBuf = [];
    // nodes whose predicate was planned against a parameter rather than a
    // value: their row estimate is an average, not a wrong statistic
    const paramNodes = new Set();
    {
      const ext = new Set((plan.parameters && plan.parameters.external) || []);
      if (ext.size) {
        for (const n of nodes) {
          if (n.spec) continue;
          for (const f of n.filters) {
            const bare = String(f.val || '').replace(/'(?:[^']|'')*'/g, "''");
            for (const m of bare.matchAll(/\$\d+/g)) {
              if (ext.has(m[0])) { paramNodes.add(n.id); break; }
            }
          }
        }
      }
    }

    for (const n of nodes) {
      if (n.spec || n.loops === 0 || n.never) continue;
      const x = n.nodeType;
      const bufHit = n.bufExcl['shared-hit'] || 0;
      const bufRead = n.bufExcl['shared-read'] || 0;
      const isScan = /^(Seq Scan|Index|Bitmap)/.test(x);

      // BitmapAnd / BitmapOr under a Bitmap Heap Scan
      if (x === 'BitmapAnd' || x === 'BitmapOr') {
        const prnt = n.parent != null ? nodes[n.parent] : null;
        if (prnt && prnt.nodeType === 'Bitmap Heap Scan') {
          const kids = realChildren(n);
          if (kids.length && kids.every(k => k.nodeType === 'Bitmap Index Scan')) {
            const spec = x === 'BitmapAnd' ? {
              relation: prnt.relationRef || prnt.relation,
              alias: prnt.alias,
              // the goal is one composite index covering all the parts
              conds: kids.flatMap(k => k.filters.map(f => ({ key: 'Filter', text: f.val }))),
            } : null;
            add(x === 'BitmapAnd' ? 'BITMAP_AND' : 'BITMAP_OR',
              [{ n: prnt, ext: rowsX(prnt) }, { n }, ...kids.map(k => ({ n: k, ext: rowsX(k) }))],
              spec);
          }
        }
      }
      // lossy bitmap
      if (x === 'Bitmap Heap Scan' && n.heapBlocksLossy > 0) {
        add('BITMAP_LOSSY', [{ n, ext: `lossy=${n.heapBlocksLossy}` }]);
      }
      // sort / hash spilled to disk
      if (/Sort$/.test(x) && n.sortSpace === 'Disk') {
        add('DISK_SORT', [{ n, ext: `${n.sortMethod}, disk ${fmtKb(n.sortSizeKb)}` }],
          null, null, { next: memNote(n.sortSizeKb) });
      }
      // Batches > 1 is the spill signal for a hash table; PostgreSQL prints a
      // "Disk Usage" figure only for some node kinds, so it cannot be required
      if (x === 'Hash' && (n.hashBatches > 1 || n.diskUsageKb > 0)) {
        const grew = n.hashBatchesOrig != null && n.hashBatches > n.hashBatchesOrig;
        const parts = [];
        if (n.hashBatches > 1) {
          parts.push(`batches=${n.hashBatches}`
            + (n.hashBatchesOrig != null ? ` (originally ${n.hashBatchesOrig})` : ''));
        }
        if (n.memUsageKb) parts.push(`peak memory ${fmtKb(n.memUsageKb)} per batch`);
        if (n.diskUsageKb) parts.push(`disk ${fmtKb(n.diskUsageKb)}`);
        add('DISK_HASH', [{ n, ext: parts.join(', ') }], null, null, {
          hyp: grew
            ? 'The batch count grew at run time (originally ' + n.hashBatchesOrig + '): the planner '
              + 'underestimated the hash side, so the build had to re-partition mid-flight.'
            : ADVICE_META.DISK_HASH.hyp,
          // Only "Disk Usage" is a measurement. The peak memory of one batch
          // times the batch count is an order of magnitude, and presenting it
          // as a volume would turn a guess into a figure.
          next: n.diskUsageKb > 0
            ? memNote(n.diskUsageKb)
              + ' A hash may use work_mem × hash_mem_multiplier (2.0 by default), so check the '
              + 'multiplier before raising work_mem itself.'
            : 'EXPLAIN does not report how much a hash wrote out — only the peak memory of one '
              + 'batch and the number of batches, so the working set is on the order of '
              + (n.hashBatches > 1 ? n.hashBatches + '× ' : '') + 'what this node was given. '
              + 'The budget for a hash is work_mem × hash_mem_multiplier (2.0 by default): '
              + 'raise them in one session (BEGIN; SET LOCAL …) and re-read the batch count, '
              + 'which drops to 1 once the hash fits.',
        });
      }
      // Memoize that caches nothing useful
      if (x === 'Memoize' && n.cache) {
        const look = n.cache.hits + n.cache.misses;
        const hitPct = look ? n.cache.hits / look * 100 : 0;
        // evictions alone say nothing: a cache that answers 90% of its lookups
        // is working even while it recycles entries. Both halves must be bad.
        const thrash = n.cache.evictions > n.cache.misses * 0.5;
        if (look >= 1000 && hitPct < 50 && (thrash || hitPct < 20)) {
          add('MEMOIZE_MISS', [{
            n,
            ext: `${look} lookups, ${hitPct.toFixed(1)}% hit`
              + `, evictions=${n.cache.evictions}`
              + (n.memUsageKb ? `, memory ${fmtKb(n.memUsageKb)}` : ''),
          }], null, null, thrash ? {
            hyp: 'Entries are evicted about as fast as they are created ('
              + n.cache.evictions + ' evictions for ' + n.cache.misses + ' misses): the cache holds '
              + (n.memUsageKb ? fmtKb(n.memUsageKb) : 'less') + ' but the key space is far larger.',
          } : {
            hyp: 'Nothing is evicted, yet the hit rate stays low: the parameter values barely repeat, '
              + 'so the Memoize only adds bookkeeping to every loop.',
          });
        }
      }
      // Limit over Sort over scan / Limit over scan
      if (x === 'Limit') {
        const chain = [n];
        let ch = firstRealChild(n);
        if (ch && /^Gather/.test(ch.nodeType)) { chain.push(ch); ch = firstRealChild(ch); }
        if (ch && /Sort$/.test(ch.nodeType)) {
          const sort = ch;
          chain.push(ch); ch = firstRealChild(ch);
          let ok = false;
          if (ch && (ch.nodeType === 'Seq Scan' || ch.nodeType.startsWith('Index'))) {
            chain.push(ch); ok = true;
          } else if (ch && ch.nodeType === 'Bitmap Heap Scan') {
            chain.push(ch);
            const bis = firstRealChild(ch);
            if (bis && bis.nodeType === 'Bitmap Index Scan') { chain.push(bis); ok = true; }
          }
          if (ok) {
            const scan = chain[chain.length - 1];
            if (n.rowsTotal * 2 < scan.rowsTotal) {
              const holder = scan.nodeType === 'Bitmap Index Scan'
                ? chain[chain.length - 2] : scan;
              const spec = sort.sortKey && holder.relation
                ? scanSpec(holder, [{ key: 'order-by', text: sort.sortKey }])
                : null;
              add('LIMIT_SORT', chain.map(c => ({
                n: c, ext: c === sort ? (c.sortKey || null) : rowsX(c),
              })), spec);
            }
          }
        } else if (ch && (ch.nodeType === 'Seq Scan' || ch.nodeType.startsWith('Index'))) {
          chain.push(ch);
          if (n.rowsTotal * 4 < ch.rowsTotal) {
            add('LIMIT_OFFSET', chain.map(c => ({ n: c, ext: rowsX(c) })));
          }
        }
      }
      // filter discards most rows
      if (/^(Bitmap Heap|Index)/.test(x)) {
        const rf = n.rowsRemovedTotal, rr = n.rowsTotal;
        if ((rf >= 100 && rr * 2 <= rf) || (rf >= 1000 && rr <= rf) || (rf >= 10000 && rr <= rf * 2)) {
          add('INDEX_DISCARD', [{
            n, ext: `rows=${rr}, removed by filter=${rf}` + ratioX(rr, rf),
          }], scanSpec(n));
        }
      }
      if (x === 'Seq Scan' && n.rowsRemoved >= 50) {
        const rf = n.rowsRemovedTotal, rr = n.rowsTotal;
        if (rf >= 100 && rr * 4 <= rf) {
          add('SEQSCAN_DISCARD', [{
            n, ext: `rows=${rr}, removed by filter=${rf}` + ratioX(rr, rf),
          }], scanSpec(n));
        }
      }
      // NOT IN (SELECT ...) evaluated as a subplan. The plan shows a negated
      // subplan, the query text says it came from NOT IN rather than from a
      // NOT EXISTS the planner could not flatten.
      if (sqlCtx && sqlCtx.forms.notIn.length
          && n.filters.some(f => /NOT \((?:hashed )?SubPlan/i.test(String(f.val || '')))) {
        add('SQL_NOTIN', [{
          n,
          ext: `${rowsX(n)}, ${sqlCtx.forms.notIn.length} NOT IN (SELECT ...) in the query`,
        }]);
      }
      // a cast the query itself wrote: the plan shows the cast but cannot say
      // who put it there, so this needs the query text. Both the column and
      // the target type must match what the query wrote for this relation.
      const nodeCasts = writtenCastsOf(n);
      if (nodeCasts && nodeCasts.size && isScan) {
        const cast = new Map();
        for (const f of n.filters) {
          if (!/Cond$|Filter$/.test(f.key)) continue;
          const bare = String(f.val || '').replace(/'(?:[^']|'')*'/g, "''");
          for (const m of bare.matchAll(/(?:^|[^\w."])\(?([A-Za-z_][\w$]*)\)?::([a-z][\w ]*)/g)) {
            const col = m[1].toLowerCase();
            const type = m[2].trim().toLowerCase();
            if (nodeCasts.has(col + '::' + type) && !cast.has(col)) cast.set(col, type);
          }
        }
        if (cast.size) {
          add('SQL_CAST', [{
            n,
            ext: [...cast].map(([c, t]) => `${c} is cast to ${t} in the query`).join(', '),
          }]);
        }
      }
      // CTE re-scanned many times
      if (x === 'CTE Scan' && n.loops > 10 && (n.rowsTotal + n.rowsRemovedTotal) > 10000) {
        add('CTE_RESCAN', [{ n, ext: `loops=${n.loops}, ${rowsX(n)}` }]);
      }
      // index scan without condition
      if (/^(Bitmap Index|Index)/.test(x) && !hasIndexCond(n)) {
        add('INDEX_FULLREAD', [{ n, ext: rowsX(n) }]);
      }
      // stale statistics. n.ratio compares the per-loop numbers, so the
      // magnitude test has to use per-loop numbers too: a parameterized probe
      // repeated 800 times with "rows=1 estimated, 0 actual" is normal — the
      // planner's estimate floor is one row and it cannot do better per
      // iteration. Scaling by loops turned that into a fleet of fake findings.
      if (/^(Seq Scan|Bitmap Index|Index)/.test(x) && n.ratio != null) {
        const loops = n.loops || 1;
        const actL = n.rows || 0, estL = n.planRows || 0;
        if (Math.max(actL, estL) > 100 && (n.ratio === Infinity || n.ratio > 100)) {
          const perLoop = loops > 1 ? `/loop over ${loops} loops` : '';
          // a generic plan is estimated without the parameter values, so the
          // miss says nothing about the statistics being stale
          const generic = paramNodes.has(n.id) ? {
            hyp: 'This node was planned against a parameter, not a value: the estimate is an '
              + 'average over all possible parameters (a generic plan), so a large miss here '
              + 'is expected rather than evidence of stale statistics.',
            next: 'Compare against a custom plan first — run the statement with literal values '
              + '(or SET LOCAL plan_cache_mode = force_custom_plan); only then look at ANALYZE '
              + 'and extended statistics.',
          } : null;
          add('ROW_ESTIMATE', [{
            n, ext: `rows-act=${actL}${perLoop}, rows-est=${estL}` + ratioX(estL, actL)
              + (generic ? ', planned from a parameter' : ''),
          }], null, null, generic);
        }
      }
      // bloat: few rows per read buffer. Buffers are normalized per loop —
      // a parameterized index lookup legitimately touches ~btree-depth
      // pages every iteration, which is not a bloat signal.
      if (/^(Seq Scan|Index)/.test(x)) {
        const br = bufHit + bufRead;
        const brPerLoop = br / (n.loops || 1);
        if (brPerLoop >= 64 && (n.rowsTotal + n.rowsRemovedTotal) < br * 8) {
          add(x === 'Seq Scan' ? 'SEQSCAN_BUFFERS' : 'INDEX_BUFFERS',
            [{ n, ext: `buffers=${br}, ${rowsX(n)}` + ratioX(n.rowsTotal + n.rowsRemovedTotal, br) }]);
        }
        if ((n.bufExcl['shared-written'] || 0) > 0) {
          // impact = the measured write cost, not the node's whole self time
          add('TABLE_WRITTEN', [{ n, ext: `shared written=${n.bufExcl['shared-written']}` }],
            null, n.ioWriteExcl || 0);
        }
      }
      // parallel workers shortfall
      if (/^Gather/.test(x) && n.workersLaunched != null && n.workersPlanned != null
          && n.workersLaunched < n.workersPlanned) {
        add('GATHER_WORKERS', [{ n, ext: `launched=${n.workersLaunched} < planned=${n.workersPlanned}` }]);
      }
      // temp spill (not already reported as lossy/disk sort/hash)
      if ((n.bufExcl['temp-written'] || 0) > 0
          && !(n.heapBlocksLossy > 0 || n.sortSpace === 'Disk' || n.diskUsageKb > 0
               || n.hashBatches > 1)) {
        // temp counters are 8 kB blocks — spell the volume out in bytes
        const kb = n.bufExcl['temp-written'] * 8;
        add('TEMP_SPILL', [{
          n, ext: `temp written=${n.bufExcl['temp-written']} blocks (${fmtKb(kb)})`,
        }], null, null, { next: memNote(kb) });
      }
      // slow node: first check whether the plan's own I/O Timings explain
      // the time (then it is an I/O problem, not a mystery), only the
      // remainder counts as "unexplained"
      if (n.timeExcl > 100) {
        const ioKnown = round3((n.ioReadExcl || 0) + (n.ioWriteExcl || 0));
        if (ioKnown >= n.timeExcl * 0.7 && n.ioReadExcl > 50) {
          const reads = bufRead + (n.bufExcl['local-read'] || 0) + (n.bufExcl['temp-read'] || 0);
          add('DISK_READ', [{
            n,
            ext: `io read=${n.ioReadExcl}ms of time=${n.timeExcl}ms`
              + (reads > 0 ? `, ${reads} read(s), ~${(n.ioReadExcl / reads).toFixed(1)} ms/read` : ''),
          }]);
        } else {
          const unexplained = n.timeExcl - ioKnown;
          // memory-speed and disk-class traffic; local buffers (temp
          // tables) count too — an INSERT moving 90k local pages is not
          // "no buffer data"
          const bm = bufHit + (n.bufExcl['local-hit'] || 0);
          const bd = bufRead + (n.bufExcl['local-read'] || 0)
            + (n.bufExcl['local-written'] || 0) + (n.bufExcl['shared-written'] || 0)
            + (n.bufExcl['temp-read'] || 0) + (n.bufExcl['temp-written'] || 0);
          // zero buffer traffic is not an alibi: a node burning seconds with
          // no I/O at all (CPU-bound expressions) is exactly this finding
          if (unexplained > 100 && (bm / 8192 + bd / 1024) < unexplained / 1000) {
            const ext = [`time=${n.timeExcl}ms`];
            if (ioKnown) ext.push(`io=${ioKnown}ms accounted, ${round3(unexplained)}ms unexplained`);
            if (bm) ext.push(`buffers in memory=${bm}`);
            if (bd) ext.push(`from disk=${bd}`);
            if (!bm && !bd && !ioKnown) ext.push('no buffer data for this node');
            // Without BUFFERS the "CPU or I/O?" question cannot be answered
            // per node at all. Firing on every slow node then produces one
            // identical card per node and buries the findings that do say
            // something — collect them into a single plan-level entry below.
            if (hasBufData) add('UNEXPLAINED_TIME', [{ n, ext: ext.join(', ') }]);
            else slowNoBuf.push(n);
          }
        }
      }
      // full read joined down to a few rows: missing FK index
      if (isScan && !/Bitmap Index/.test(x) && !n.filters.length
          && (n.loops || 1) === 1 && n.rowsTotal >= 100 && n.parent != null) {
        let p = nodes[n.parent];
        let chain0 = [n];
        if (p && p.nodeType === 'Materialize' && p.parent != null) { chain0.unshift(p); p = nodes[p.parent]; }
        const joinSpec = join => {
          const conds = join.filters
            .filter(f => /Cond$|Join Filter/.test(f.key))
            .map(f => ({ key: 'Filter', text: f.val })); // treat the join key as the condition to index
          return conds.length
            ? { relation: n.relationRef || n.relation, alias: n.alias, conds } : null;
        };
        // anti-join first: "Hash Anti Join" would also match the generic
        // hash/merge pattern below
        if (p && /Anti Join$/.test(p.nodeType) && p.rowsTotal * 4 < n.rowsTotal) {
          add('ANTIJOIN_FULLREAD', [{ n: p, ext: rowsX(p) }, ...chain0.map(c => ({ n: c, ext: rowsX(c) }))],
            joinSpec(p));
        } else if (p && /^(Hash|Merge).*Join$/.test(p.nodeType) && p.rowsTotal * 4 < n.rowsTotal) {
          add('JOIN_FULLREAD', [{ n: p, ext: rowsX(p) }, ...chain0.map(c => ({ n: c, ext: rowsX(c) }))],
            joinSpec(p));
        }
      }
      // nested-loop join filter discarding almost every examined pairing
      if (/^Nested Loop/.test(x) && n.rowsRemovedBy['Join Filter']) {
        const rf = Math.round(n.rowsRemovedBy['Join Filter'] * (n.loops || 1));
        const kept = n.rowsTotal;
        if (rf >= 1000 && kept * 10 <= rf) {
          const kids = realChildren(n);
          let inner = kids.length > 1 ? kids[kids.length - 1] : null;
          const heads = [{ n, ext: `kept rows=${kept}, removed by join filter=${rf}` + ratioX(kept, rf) }];
          let spec = null;
          if (inner) {
            if (inner.nodeType === 'Materialize') {
              heads.push({ n: inner });
              const mc = firstRealChild(inner);
              if (mc) inner = mc;
            }
            heads.push({ n: inner, ext: rowsX(inner) });
            const jf = n.filters.find(f => f.key === 'Join Filter');
            if (jf && inner.relation) {
              spec = {
                relation: inner.relationRef || inner.relation,
                alias: inner.alias,
                conds: [{ key: 'Filter', text: jf.val }],
              };
            }
          }
          add('NESTLOOP_DISCARD', heads, spec);
        }
      }
      // redundant nested sort
      if (x === 'Sort' && n.sortKey && n.parent != null) {
        let p = nodes[n.parent];
        const chain = [n];
        if (p && p.nodeType.endsWith('Subquery Scan') && p.parent != null) {
          chain.push(p); p = nodes[p.parent];
        }
        if (p && p.nodeType === 'Sort' && p.sortKey) {
          add('REDUNDANT_SORT', [{ n: p, ext: p.sortKey }, ...chain.map(c => ({ n: c, ext: c.sortKey || null }))]);
        }
      }
      // redundant regrouping
      if (/Aggregate$/.test(x) && n.groupKey && !n.filters.length) {
        const ch = firstRealChild(n);
        if (ch && /Aggregate$/.test(ch.nodeType) && ch.groupKey
            && ch.groupKey.replace(/^\((.*)\)$/, '$1') === n.groupKey.replace(/^\((.*)\)$/, '$1')) {
          add('REDUNDANT_GROUP', [{ n, ext: n.groupKey }, { n: ch, ext: ch.groupKey }]);
        }
      }
      // duplicated subtree
      if (n.children.length && n.id > 0 && !/^(Insert|Update|Delete|Merge|Function Scan|Values Scan)$/.test(x)
          && !sigDone.has(n.id)) {
        const sig = [];
        const ids = [];
        let hasRel = false;
        (function walk(id, base) {
          const c = nodes[id];
          if (c.spec) { for (const g of c.children) walk(g, base); return; }
          hasRel = hasRel || !!c.relation;
          ids.push(c.id);
          sig.push((c.depth - base) + ':' + c.nodeType + ':' + (c.relation || '') + ':' + (c.index || ''));
          for (const g of c.children) walk(g, base);
        })(n.id, n.depth);
        if (hasRel && ids.length >= 2) {
          const key = sig.join('|');
          const main = sigHash.get(key);
          if (main === undefined) {
            sigHash.set(key, ids.slice());
          } else {
            for (const id of ids) sigDone.add(id);
            add('REPEATED_WORK', ids.map((id, i) => ({ n: nodes[id], ext: 'same as node #' + main[i] })));
          }
        }
      }
    }

    // -- residual-finding cleanup. UNEXPLAINED_TIME says "nothing here explains the
    // time"; where the same node already carries a measured cause, the
    // residual restates it, double-counts the milliseconds in the ranking
    // and pushes the actionable card down the list.
    const explained = new Set();
    {
      for (const a of advice) {
        if (!CAUSE_CODES.has(a.code)) continue;
        for (const h of a.nodes) explained.add(h.id);
      }
      const dropped = new Set();
      advice = advice.filter(a => {
        if (a.code !== 'UNEXPLAINED_TIME') return true;
        if (!a.nodes.every(h => explained.has(h.id))) return true;
        dropped.add(a);
        return false;
      });
      if (dropped.size) {
        for (const n of nodes) {
          if (n.advice) n.advice = n.advice.filter(a => !dropped.has(a));
        }
      }
    }

    // plan-level advice
    const planEntry = (code, ext, impactMs, impactBase, heads, over) => {
      const meta = ADVICE_META[code];
      const entry = {
        code, badge: badgeOf(code), sev: meta.sev,
        // the finding is about the plan, not about the nodes it names
        scope: 'plan',
        obs: meta.obs, hyp: meta.hyp || null, next: meta.next || null,
        nodes: (heads || []).map(h => ({ id: h.n.id, ext: h.ext || null })), ext,
        impactMs, impactBase, // consumed by the gating pass below
      };
      if (over) Object.assign(entry, over);
      advice.push(entry);
      for (const h of (heads || [])) (h.n.advice ??= []).push(entry);
      return entry;
    };
    // one entry for "the plan spends its time somewhere the plan cannot show".
    // Nodes whose time another rule already explains are not part of it.
    // (self times on a truncated plan are inflated by the missing children,
    // so the "unexplained time" arithmetic does not hold there)
    const unexplainedSlow = localOnly ? [] : slowNoBuf.filter(n => !explained.has(n.id));
    if (unexplainedSlow.length) {
      unexplainedSlow.sort((a, b) => b.timeExcl - a.timeExcl);
      const top = unexplainedSlow.slice(0, 8);
      const sum = unexplainedSlow.reduce((s, n) => s + n.timeExcl, 0);
      planEntry('UNEXPLAINED_TIME',
        `${unexplainedSlow.length} node(s), no buffer data to explain their self time`,
        sum, null,
        top.map(n => ({ n, ext: `time=${n.timeExcl}ms` })),
        {
          obs: 'Time is concentrated in nodes whose cost the plan cannot account for: '
            + 'this EXPLAIN carries no BUFFERS, so I/O and memory traffic per node are unknown.',
          hyp: 'Without buffer counters, CPU-heavy expressions, cold reads, lock waits and a '
            + 'saturated host all look identical.',
          next: 'Re-run with EXPLAIN (ANALYZE, BUFFERS) to split I/O from CPU; correlate with '
            + 'pg_stat_activity wait events if the time stays unexplained.',
        });
    }
    if (plan.executionTime != null && plan.totals.time != null) {
      const overhead = plan.executionTime - plan.totals.time;
      if (overhead > 20 && overhead / plan.executionTime >= 0.8) {
        planEntry('OUTSIDE_PLAN',
          `${(overhead / plan.executionTime * 100).toFixed(1)}% of ${plan.executionTime.toFixed(3)}ms is outside the plan`,
          overhead, plan.executionTime);
      }
    }
    // planning is part of what the caller waits for: judge it against the
    // whole latency, not only against the case where it exceeds execution
    {
      const execRef = plan.executionTime != null ? plan.executionTime : plan.totals.time;
      const pt = plan.planningTime;
      if (pt != null && execRef != null && pt > 20 && pt >= (pt + execRef) * 0.1) {
        // the query text settles whether "use prepared statements" is advice
        // or noise: a statement already sent with $N is being re-planned for
        // another reason
        const sql = plan.sql && plan.sql.bound ? plan.sql : null;
        let over = null;
        if (sql && sql.params.count > 0) {
          over = {
            hyp: 'The statement is already parameterized ($1…), so this planning cost is not '
              + 'a missing prepared statement: either the prepared statement is not reused '
              + 'across calls, or the server keeps choosing a custom plan for it.',
            next: 'Check that the client re-uses the prepared statement instead of re-preparing '
              + 'it; then compare plan_cache_mode = force_generic_plan. If the table is '
              + 'partitioned, check how many partitions survive pruning at plan time.',
          };
        } else if (sql && sql.predicateLiterals > 0 && sql.params.count === 0) {
          over = {
            hyp: 'The query text carries literal values rather than parameters. If it is sent '
              + 'that way on every call the server re-plans it every time — though the plan '
              + 'cannot show whether the client prepares and reuses the statement.',
            next: 'Send the varying values as parameters and reuse one prepared statement; if it '
              + 'is prepared already, check that the client keeps the handle instead of '
              + 're-preparing per call.',
          };
        }
        planEntry('PLANNING_TIME',
          `planning ${round3(pt)}ms of ${round3(pt + execRef)}ms total latency `
          + `(${(pt / (pt + execRef) * 100).toFixed(1)}%), execution ${round3(execRef)}ms`
          + (over ? (sql.params.count > 0
            ? `, query uses ${sql.params.count} parameter(s)`
            : ', query text carries literals, not parameters') : ''),
          pt, pt + execRef, null, over);
      }
    }
    // JIT compilation is charged to execution time but lives outside the tree
    if (plan.jit && plan.jit.total != null) {
      const execRef = plan.executionTime != null ? plan.executionTime : plan.totals.time;
      const jt = plan.jit.total;
      if (execRef != null && jt >= 5 && jt >= execRef * 0.1) {
        const opts = Object.entries(plan.jit.options || {})
          .filter(([, v]) => v).map(([k]) => k);
        const slow = Object.entries(plan.jit.timing || {})
          .filter(([k]) => k !== 'total').sort((a, b) => b[1] - a[1])[0];
        planEntry('JIT_TIME',
          `JIT ${round3(jt)}ms of ${round3(execRef)}ms execution (${(jt / execRef * 100).toFixed(1)}%)`
          + (plan.jit.functions != null ? `, ${plan.jit.functions} functions` : '')
          + (slow ? `, most of it in ${slow[0]} (${round3(slow[1])}ms)` : '')
          + (opts.length ? `; enabled: ${opts.join(', ')}` : ''),
          jt, execRef);
      }
    }

    // -- impact gating: share of plan time attributable to the flagged nodes,
    // combined with an absolute floor. Tiny findings are demoted to 'minor'
    // so they never distract from material bottlenecks.
    const totalTime = plan.totals.time;
    for (const a of advice) {
      let ms = a.impactMs != null ? a.impactMs : null;
      // on a truncated plan the self times are upper bounds, so a share of
      // the total would be fiction — rank by absolute time, claim no level
      let base = localOnly ? null : (a.impactBase != null ? a.impactBase : totalTime);
      delete a.impactMs; delete a.impactBase;
      if (ms == null) {
        let sum = 0, has = false;
        for (const id of new Set(a.nodes.map(h => h.id))) {
          const n = nodes[id];
          if (!n.spec && n.timeExcl != null) { sum += n.timeExcl; has = true; }
        }
        ms = has ? sum : null;
      }
      const pct = ms != null && base ? ms / base * 100 : null;
      let level = 'unknown'; // no runtime data: nothing to gate on
      if (ms != null) {
        if ((pct != null && pct < 2) || ms < 1) level = 'minor';
        else if (pct == null) level = 'low';
        else if (pct >= 20) level = 'high';
        else if (pct >= 5) level = 'medium';
        else level = 'low';
      }
      a.impact = {
        ms: ms != null ? round3(ms) : null,
        pct: pct != null ? Math.round(pct * 10) / 10 : null,
        level,
      };
    }
    // material findings first (by attributable time), minor section last
    const byImpact = (x, y) => {
      const mx = x.impact.level === 'minor' ? 1 : 0;
      const my = y.impact.level === 'minor' ? 1 : 0;
      if (mx !== my) return mx - my;
      return (y.impact.ms || 0) - (x.impact.ms || 0);
    };
    advice.sort(byImpact);

    // -- family collapsing: a big plan can trigger the same rule on dozens
    // of nodes (archive sweep: 20× UNEXPLAINED_TIME, 40× ROW_ESTIMATE in one plan).
    // Keep the three highest-impact entries per code and roll the rest into
    // one aggregate entry; DDL candidates from rolled-up entries survive on
    // the aggregate, and row badges still mark every affected node.
    {
      advice.forEach((a, i) => { a._ord = i; });
      const byCode = new Map();
      for (const a of advice) {
        if (!byCode.has(a.code)) byCode.set(a.code, []);
        byCode.get(a.code).push(a);
      }
      const collapsed = [];
      for (const group of byCode.values()) {
        if (group.length <= 4) { collapsed.push(...group); continue; }
        const kept = group.slice(0, 3), tail = group.slice(3);
        collapsed.push(...kept);
        const ms = tail.reduce((s, a) => s + (a.impact.ms || 0), 0);
        const hasMs = tail.some(a => a.impact.ms != null);
        // same base as the individual entries: on a truncated plan the self
        // times are upper bounds, so a share of the total stays unknown
        const pct = hasMs && !localOnly && totalTime ? ms / totalTime * 100 : null;
        let level = 'unknown';
        if (hasMs) {
          if ((pct != null && pct < 2) || ms < 1) level = 'minor';
          else if (pct == null) level = 'low';
          else if (pct >= 20) level = 'high';
          else if (pct >= 5) level = 'medium';
          else level = 'low';
        }
        const idxs = [];
        const seenIdx = new Set();
        for (const a of tail) {
          for (const ix of a.idxs || []) {
            const key = ix.def || ix.name;
            if (seenIdx.has(key)) continue;
            seenIdx.add(key);
            idxs.push(ix);
          }
        }
        collapsed.push({
          _ord: tail[0]._ord,
          code: tail[0].code, badge: tail[0].badge, sev: tail[0].sev, agg: tail.length,
          obs: tail.length + ' more nodes match this pattern'
            + (hasMs ? ', combined self time ' + round3(ms) + ' ms'
              + (pct != null ? ' (' + (Math.round(pct * 10) / 10) + '% of total)' : '') : ''),
          hyp: null,
          next: 'The top entries above show the same pattern in detail; '
            + 'row badges mark every affected node in the plan table',
          nodes: tail.reduce((s, a) => s.concat(a.nodes), []),
          ext: [],
          impact: { ms: hasMs ? round3(ms) : null,
                    pct: pct != null ? Math.round(pct * 10) / 10 : null, level },
          idxs,
        });
      }
      advice = collapsed;
      advice.sort((x, y) => byImpact(x, y) || (x._ord || 0) - (y._ord || 0));
      advice.forEach(a => { delete a._ord; });
    }

    plan.advice = advice;
  }

  /* ------------------------------------------------------------------ *
   * SQL context — what the accompanying query text adds to the plan.
   * Everything here is gated on the pair actually belonging together:
   * a plan analyzed against somebody else's query is worse than no query.
   * ------------------------------------------------------------------ */

  function buildSqlContext(plan) {
    plan.sql = null;
    if (!Sql || !plan.query) return;
    const diag = (code, severity, message, samples) => {
      plan.diagnostics.push({
        code, severity, message, count: 1,
        samples: samples ? samples.slice(0, 3).map(x => String(x).slice(0, 200)) : [],
      });
    };
    let sc, bd;
    try {
      sc = Sql.scan(plan.query);
      bd = Sql.bind(sc, plan);
    } catch (e) {
      diag('sql_unparsed', 'info',
        'The SQL text could not be scanned: findings that would rely on the query are off');
      return;
    }
    if (bd.reason === 'multi-statement') {
      diag('sql_multi_statement', 'warn',
        'The SQL text contains ' + sc.statements + ' statements while a plan describes one of '
        + 'them, and nothing in the plan says which: relations, casts and parameters from the '
        + 'other statements would be attributed to this one. Findings that rely on the query '
        + 'are off — paste the single statement this plan belongs to.');
    } else if (bd.reason === 'partial') {
      diag('sql_mismatch', 'warn',
        'The SQL text and the plan match only partially ('
        + bd.sqlOnly.slice(0, 3).join(', ')
        + (bd.sqlOnly.length > 3 ? ', …' : '')
        + ' named in the query but not read by the plan): either the two inputs are from '
        + 'different statements, or the planner removed those relations (view expansion, join '
        + 'elimination). The difference is not visible from here, so findings that rely on the '
        + 'query are off.', bd.sqlOnly);
    } else if (bd.reason === 'plan-only') {
      diag('sql_mismatch', 'warn',
        'The plan reads relations the query never names ('
        + bd.planOnly.slice(0, 3).join(', ')
        + (bd.planOnly.length > 3 ? ', …' : '')
        + '): the two inputs are not the same statement, or the plan expands a view. '
        + 'Findings that rely on the query are off.', bd.planOnly);
    } else if (bd.reason === 'no-relations') {
      diag('sql_mismatch', 'warn',
        'The SQL text names no relation the plan could read: findings that rely on the query are off');
    }
    // Map plan nodes onto the FROM item they came from, so a node can be
    // pointed back at the fragment of the query that produced it. An alias
    // reused in several subqueries is marked rather than guessed at.
    let matchedNodes = 0;
    if (bd.bound) {
      const fold = Sql.fold;
      const uses = new Map();
      for (const r of sc.relations) {
        const k = r.alias || r.name;
        if (k) uses.set(k, (uses.get(k) || 0) + 1);
      }
      for (const n of plan.nodes) {
        if (n.spec || !n.relation) continue;
        const alias = n.alias ? fold(n.alias) : null;
        const name = fold(String(n.relation).split('.').pop());
        // An alias may only speak for a node whose relation agrees with the
        // FROM item it names: "payments o" is not the query's "orders o",
        // however well the aliases line up.
        const viaAlias = alias ? bd.byAlias.get(alias) : null;
        const aliasOk = viaAlias && (viaAlias.kind !== 'table' || viaAlias.name === name);
        // a CTE Scan belongs to the CTE definition rather than to whichever
        // reference of it happens to come first in the text
        const parent = Sql.parentAlias(alias);
        const hit = bd.byCte.get(name)
          || (aliasOk ? viaAlias : null)
          || bd.byName.get(name)
          // a partitioned/inherited child, recognized by the alias PostgreSQL
          // derives from the parent's ("orders o" -> "orders_p2026_08 o_1")
          || (parent ? bd.byAlias.get(parent) : null)
          || null;
        if (!hit) continue;
        n.sqlSpan = { s: hit.s, e: hit.e, ref: hit.ref || null };
        if (uses.get(alias || name) > 1) n.sqlSpan.ambiguous = true;
        matchedNodes++;
      }

      // Attribute every cast written in the query to the FROM item it names.
      // A bare "id::numeric" belongs to nobody in particular, so it counts
      // only when the statement reads a single source; otherwise the column
      // name alone would hand one relation's cast to another's index.
      const sources = sc.relations.filter(r => r.kind === 'table');
      const soleSource = sources.length === 1 ? sources[0] : null;
      const castsFor = new Map();     // FROM-item span key -> Set('col::type')
      for (const c of sc.casts) {
        const dot = c.qualified.lastIndexOf('.');
        const qual = dot > 0 ? fold(c.qualified.slice(0, dot)) : null;
        const target = qual
          ? (bd.byAlias.get(qual) || bd.byName.get(qual) || null)
          : soleSource;
        if (!target) continue;        // ambiguous: never used
        const key = target.s + ':' + target.e;
        if (!castsFor.has(key)) castsFor.set(key, new Set());
        castsFor.get(key).add(c.col + '::' + c.type);
      }
      for (const n of plan.nodes) {
        if (!n.sqlSpan) continue;
        const set = castsFor.get(n.sqlSpan.s + ':' + n.sqlSpan.e);
        if (set && set.size) n.sqlCasts = [...set].sort();
      }
    }
    plan.sql = {
      bound: bd.bound,
      reason: bd.reason,
      coverage: Math.round(bd.coverage * 100) / 100,
      matchedNodes,
      statements: sc.statements,
      params: sc.params,
      predicateLiterals: sc.predicateLiterals,
      relations: sc.relations,
      ctes: sc.ctes,
      casts: sc.casts,
      forms: sc.forms,
      unmatched: bd.sqlOnly,
      planOnly: bd.planOnly,
    };
  }

  /* ------------------------------------------------------------------ *
   * EXPLAIN coaching — which missing options would answer open questions.
   * Never suggests an unsafe one-click command: for DML the side-effect
   * warning is explicit.
   * ------------------------------------------------------------------ */

  function buildCoaching(plan) {
    const coaching = [];
    // a running-query snapshot or an incomplete paste cannot be re-run
    // with different options in any meaningful way
    if (plan.inProgress || plan.truncated) { plan.coaching = coaching; return; }
    const nodes = plan.nodes;
    const isDml = nodes.length && /^(Insert|Update|Delete|Merge)$/.test(nodes[0].nodeType);
    const hasActual = nodes.some(n => n.loops != null || n.never);
    const hasTimes = nodes.some(n => n.timeTotal != null);
    const hasBuf = nodes.some(n => Object.keys(n.buf).length > 0);
    if (!hasActual) {
      coaching.push({
        option: 'ANALYZE, BUFFERS',
        reason: 'the plan carries no runtime data — actual rows, loops, timing and I/O are unknown, so only planner estimates can be analyzed',
        warning: isDml
          ? 'EXPLAIN ANALYZE executes the statement. For INSERT/UPDATE/DELETE/MERGE run it inside BEGIN … ROLLBACK, or against a disposable copy.'
          : null,
      });
    } else {
      if (!hasTimes) {
        coaching.push({
          option: 'TIMING',
          reason: 'per-node timings are missing (TIMING OFF): time-based analysis is unavailable',
          warning: null,
        });
      }
      if (!hasBuf) {
        coaching.push({
          option: 'BUFFERS',
          reason: 'no buffer statistics: I/O and memory traffic per node are invisible',
          warning: null,
        });
      }
    }
    plan.coaching = coaching;
  }

  /* ------------------------------------------------------------------ *
   * Entry point
   * ------------------------------------------------------------------ */

  // Known executor node names, used to validate that input is credible as a
  // PostgreSQL plan when it carries no cost/actual clause (COSTS OFF).
  const RE_KNOWN_NODE = new RegExp('^(?:Parallel |Partial |Finalize |Async )*(?:'
    + ['Seq Scan', 'Index Only Scan', 'Index Scan', 'Bitmap Heap Scan',
      'Bitmap Index Scan', 'Tid Scan', 'Tid Range Scan', 'Sample Scan',
      'Function Scan', 'Table Function Scan', 'Values Scan', 'CTE Scan',
      'WorkTable Scan', 'Named Tuplestore Scan', 'Foreign Scan', 'Custom Scan',
      'Subquery Scan', 'Result', 'ProjectSet', 'Insert', 'Update', 'Delete',
      'Merge Append', 'Merge', 'Append', 'Recursive Union', 'BitmapAnd',
      'BitmapOr', 'Nested Loop', 'Hash', 'Materialize', 'Memoize',
      'Incremental Sort', 'Sort', 'Group', 'Unique', 'Gather Merge', 'Gather',
      'SetOp', 'HashSetOp', 'LockRows', 'Limit', 'WindowAgg', 'Aggregate',
      'GroupAggregate', 'HashAggregate', 'MixedAggregate'].join('|')
    + ')\\b');

  const looksLikePlanNode = n => n.costTotal != null || n.loops != null
    || n.never || n.inProgress || RE_KNOWN_NODE.test(n.head);

  // attribute keys that only ever appear inside a node's detail block —
  // a plan whose FIRST line is one of these lost its head node above
  const RE_ATTRLINE_HEAD = new RegExp('^(?:'
    + ['Sort Key', 'Presorted Key', 'Group Key', 'Sort Method', 'Buffers',
      'Output', 'Filter', 'Join Filter', 'One-Time Filter', 'Hash Cond',
      'Merge Cond', 'Index Cond', 'Recheck Cond', 'TID Cond', 'Order By',
      'I\\/O Timings', 'Rows Removed by [A-Za-z ]+', 'Heap Blocks',
      'Heap Fetches', 'Worker \\d+', 'Workers Planned', 'Workers Launched',
      'Cache Key', 'Cache Mode', 'Buckets', 'Batches', 'Peak Memory Usage',
      'Storage', 'Group By', 'Partition By'].join('|')
    + ')\\s*:');

  const MAX_INPUT_BYTES = 8 * 1024 * 1024;
  const MAX_QUERY_BYTES = 1024 * 1024;
  const MAX_NODES = 50000;

  // UTF-8 size of a string; String.length counts UTF-16 code units, which
  // undercounts non-ASCII input by up to 3x
  const byteLength = s => (typeof TextEncoder !== 'undefined'
    ? new TextEncoder().encode(s).length
    : Buffer.byteLength(s, 'utf8'));

  function checkSize(s, limit, what) {
    if (s == null) return;
    // cheap pre-checks: chars <= bytes <= 3*chars for non-surrogate text
    if (s.length <= limit / 3) return;
    const bytes = s.length > limit ? s.length : byteLength(s);
    if (bytes > limit) {
      throw new Error(what + ' too large (' + Math.round(bytes / 1024 / 1024) + ' MB, limit '
        + limit / 1024 / 1024 + ' MB)');
    }
  }

  function noteSkippedFields(parsed, skipped) {
    if (!skipped || !skipped.length) return;
    const keys = [...new Set(skipped)];
    parsed.diagnostics.push({
      code: 'unsupported_field', severity: 'info',
      message: 'Structured field(s) are not represented in the normalized model yet: '
        + keys.join(', '),
      count: skipped.length, samples: keys.slice(0, 3),
    });
  }

  // parse(input[, opts])
  //   opts.query    — SQL text supplied separately from the plan; overrides
  //                   a Query Text found inside the input.
  //   opts.tolerant — accept input whose root does not look like a plan
  //                   node instead of throwing.
  function parse(input, opts) {
    checkSize(input, MAX_INPUT_BYTES, 'Input');
    if (opts && opts.query != null) checkSize(String(opts.query), MAX_QUERY_BYTES, 'SQL text');
    let s = preclean(input);
    let duration = null;
    let query = null;
    let format = 'text';

    // strip auto_explain prefix line
    const nl = s.indexOf('\n');
    const first = (nl === -1 ? s : s.slice(0, nl)).trim();
    const dm = RE_DURATION.exec(first);
    if (dm) {
      duration = Number(dm[1]);
      s = nl === -1 ? '' : s.slice(nl + 1);
    }

    // "Query Text:" preamble (text/yaml auto_explain): capture up to the
    // first line that starts the actual plan
    const qtPos = s.search(/(^|\n)\s*Query Text:/);
    if (qtPos !== -1) {
      const qtStart = s.indexOf('Query Text:', qtPos) + 'Query Text:'.length;
      // plan starts at first subsequent line that looks like a node, JSON or "Plan:"
      const rest = s.slice(qtStart);
      const planStart = rest.search(
        /\n(?=[{[]|Plan:|- Plan:|\s*[A-Z][A-Za-z ()"]*?\s+\(cost=|\s*[A-Z][A-Za-z ()."\w]*?\s+\(actual|\s*(?:Insert|Update|Delete|Merge|Result|Append|Limit|Sort|Aggregate|HashAggregate|GroupAggregate|WindowAgg|Nested Loop|Hash|Merge|Seq Scan|Index|Bitmap|Gather|Unique|LockRows|CTE Scan|Values Scan|Function Scan|Materialize|Memoize|SetOp|Group|Recursive Union|ProjectSet|Incremental Sort|Tid Scan|Sample Scan|Foreign Scan|Custom Scan|Subquery Scan|WorkTable Scan)\b)/
      );
      if (planStart !== -1) {
        query = rest.slice(0, planStart).trim().replace(/^"|"$/g, '');
        s = rest.slice(planStart + 1);
      } else {
        query = rest.trim();
        s = '';
      }
    }

    let parsed;
    const t = s.trim();
    if (t.startsWith('{') || t.startsWith('[')) {
      format = 'json';
      let json;
      try { json = JSON.parse(t); }
      catch (e) {
        try { json = JSON.parse(t.replace(/""/g, '"')); }
        catch (e2) { throw new Error('Invalid JSON plan: ' + e.message); }
      }
      const conv = jsonToText(json);
      parsed = parseText(conv.text);
      parsed.query = conv.query;
      parsed.textForm = conv.text;
      noteSkippedFields(parsed, conv.skipped);
    } else if (/^(- )?Plan:\s*$/m.test(t) && /^\s+(Node Type|"Node Type"):/m.test(t)) {
      format = 'yaml';
      const y = parseYaml(t);
      const rootObj = Array.isArray(y) ? y[0] : y;
      const conv = jsonToText(rootObj);
      parsed = parseText(conv.text);
      parsed.query = conv.query;
      parsed.textForm = conv.text;
      noteSkippedFields(parsed, conv.skipped);
    } else {
      parsed = parseText(s);
      parsed.textForm = s.split('\n').filter(l => l.trim().length).join('\n');
    }

    // Query Identifier is a signed int64; JSON.parse/Number lose precision
    // beyond 2^53, so the exact value is taken lexically from the source
    let queryId = null;
    {
      const m = format === 'json'
        ? /"Query Identifier"\s*:\s*(-?\d+)/.exec(t)
        : /^\s*"?Query Identifier"?:\s*"?(-?\d+)"?\s*$/m.exec(t);
      if (m) queryId = m[1];
    }
    if (queryId) {
      const e = parsed.ext.find(x => x.key === 'Query Identifier');
      if (e) {
        e.value = queryId;
        e.lines = ['Query Identifier: ' + queryId];
      }
    }

    if (!parsed.nodes.length) {
      throw new Error('No plan nodes recognized in input');
    }
    if (parsed.nodes.length > MAX_NODES) {
      throw new Error('Plan too large (' + parsed.nodes.length
        + ' nodes, limit ' + MAX_NODES + ')');
    }
    if (!(opts && opts.tolerant)) {
      const root = parsed.nodes[0];
      const credible = looksLikePlanNode(root)
        || parsed.nodes.some(n => n !== root && !n.spec && looksLikePlanNode(n));
      if (!credible) {
        throw new Error('Input does not look like a PostgreSQL execution plan'
          + ' (no known node types or cost/actual clauses found);'
          + ' pass {tolerant: true} to force parsing');
      }
    }
    // head-cut detection: the plan was pasted without its first line(s) —
    // the "root" we built is really an attribute line (Sort Key:, Buffers:,
    // ...) while credible nodes follow below it. Note RE_KNOWN_NODE cannot
    // be used here: "Sort Key" word-boundary-matches the node name "Sort".
    {
      const root = parsed.nodes[0];
      if (root && !root.spec
          && root.costTotal == null && root.loops == null
          && !root.never && !root.inProgress
          && RE_ATTRLINE_HEAD.test(root.head)
          && parsed.nodes.some(n => n !== root && !n.spec && looksLikePlanNode(n))) {
        parsed.truncated = true;
        parsed.diagnostics.push({
          code: 'truncated_input', severity: 'warn',
          message: 'The plan starts with attribute lines: its head node is missing; only node-local recommendations are produced',
          count: 1, samples: [String(root.head).slice(0, 200)],
        });
      }
    }

    const externalQuery = opts && opts.query != null && String(opts.query).trim()
      ? String(opts.query).trim() : null;
    const plan = {
      nodes: parsed.nodes,
      ext: parsed.ext,
      triggers: parsed.triggers,
      text: parsed.textForm,
      query: externalQuery != null ? externalQuery
        : query != null ? query : parsed.query,
      duration,
      format,
      diagnostics: parsed.diagnostics || [],
      truncated: !!parsed.truncated,
      // exact decimal string (or null) — safe to match against
      // pg_stat_statements.queryid / query_texts keys
      queryId: queryId != null ? queryId
        : (parsed.ext.find(x => x.key === 'Query Identifier') || {}).value || null,
    };
    plan.inProgress = parsed.nodes.some(n => n.inProgress);
    analyze(plan);
    buildStats(plan);
    buildDomain(plan);
    // the SQL context has to exist before the advisor runs: several rules
    // change what they claim once the query text is known
    buildSqlContext(plan);
    buildAdvice(plan);
    buildCoaching(plan);
    if (Expr) {
      try { plan.schema = Expr.buildSchema(plan); }
      catch (e) { plan.schema = null; }
    }
    return plan;
  }

  return {
    parse,
    BUFFER_COLS,
    _internal: { parseYaml, jsonToText, parseText },
  };
}));
