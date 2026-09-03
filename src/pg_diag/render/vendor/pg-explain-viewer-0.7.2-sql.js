/*
 * pgplan-sql.js — shallow scanner for the SQL text that accompanies a plan.
 *
 * NOT a SQL parser, and deliberately never will be. It answers the few
 * questions a plan alone cannot answer:
 *   - which FROM/JOIN item an alias in the plan came from, and where in the
 *     text it is written, so a node can be pointed back at the query;
 *   - whether the statement was sent with parameters ($N) or with literals,
 *     which decides how a row-estimate miss and a planning cost are explained;
 *   - whether a cast in a predicate was written by the author or injected by
 *     the planner, which decides whether an index on the column can help;
 *   - a few shapes the plan erases (NOT IN vs NOT EXISTS).
 *
 * Everything is recorded with source offsets so the UI can highlight the
 * fragment. Nothing here produces SQL: the scanner reads, never writes.
 *
 * Pure JS, zero dependencies, UMD.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.PgPlanSql = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ================= lexer ================= */

  // Token: {t, v, s, e} — type, text, start offset, end offset.
  // Types: word qid str num param op punct semi cast
  // Whitespace and comments are dropped; every token keeps its offsets, so a
  // reported span always points into the original, unmodified text.

  // PostgreSQL allows letters, digits, _, $ and any non-ASCII byte in an
  // unquoted identifier
  const RE_IDENT_START = /[A-Za-z_\u0080-\uFFFF]/;
  const RE_IDENT = /[A-Za-z0-9_$\u0080-\uFFFF]/;
  const IS_DIGIT = c => c >= '0' && c <= '9';
  const OP_CHARS = '+-*/<>=~!@#%^&|`?';

  function lex(sql) {
    const out = [];
    const n = sql.length;
    let i = 0;
    while (i < n) {
      const c = sql[i];
      if (c === ' ' || c === '\t' || c === '\n' || c === '\r' || c === '\f') { i++; continue; }
      if (c === '-' && sql[i + 1] === '-') {                    // line comment
        const nl = sql.indexOf('\n', i);
        i = nl < 0 ? n : nl + 1;
        continue;
      }
      if (c === '/' && sql[i + 1] === '*') {                    // block comment (nests)
        let depth = 1;
        i += 2;
        while (i < n && depth > 0) {
          if (sql[i] === '/' && sql[i + 1] === '*') { depth++; i += 2; }
          else if (sql[i] === '*' && sql[i + 1] === '/') { depth--; i += 2; }
          else i++;
        }
        continue;
      }
      const start = i;
      if (c === '$') {
        // dollar-quoted string ($$...$$ / $tag$...$tag$) before the $N
        // parameter; a bare "$" that is neither falls through to the operator
        const m = /^\$(?:[A-Za-z_\u0080-\uFFFF][A-Za-z0-9_\u0080-\uFFFF]*)?\$/.exec(sql.slice(i));
        if (m) {
          const tag = m[0];
          const close = sql.indexOf(tag, i + tag.length);
          i = close < 0 ? n : close + tag.length;
          out.push({ t: 'str', v: sql.slice(start, i), s: start, e: i });
          continue;
        }
        if (IS_DIGIT(sql[i + 1])) {
          i++;
          while (i < n && IS_DIGIT(sql[i])) i++;
          out.push({ t: 'param', v: sql.slice(start, i), s: start, e: i });
          continue;
        }
      }
      // string literal, including the E'', N'' and U&'' prefixes
      const strPrefix = /^(?:[EeNn]'|[Uu]&')/.exec(sql.slice(i, i + 3));
      if (c === "'" || strPrefix) {
        const backslashEscapes = /^[Ee]'/.test(sql.slice(i, i + 2));
        i = sql.indexOf("'", start) + 1;
        for (;;) {
          if (i >= n) break;
          if (backslashEscapes && sql[i] === '\\') { i += 2; continue; }
          if (sql[i] === "'") {
            if (sql[i + 1] === "'") { i += 2; continue; }
            i++;
            break;
          }
          i++;
        }
        out.push({ t: 'str', v: sql.slice(start, i), s: start, e: i });
        continue;
      }
      if (c === '"') {                                          // quoted identifier
        i++;
        for (;;) {
          if (i >= n) break;
          if (sql[i] === '"') {
            if (sql[i + 1] === '"') { i += 2; continue; }
            i++;
            break;
          }
          i++;
        }
        out.push({ t: 'qid', v: sql.slice(start, i), s: start, e: i });
        continue;
      }
      if (IS_DIGIT(c)) {
        while (i < n && /[0-9.]/.test(sql[i])) i++;
        if (/[eE]/.test(sql[i] || '') && /[0-9+-]/.test(sql[i + 1] || '')) {
          i += 2;
          while (i < n && IS_DIGIT(sql[i])) i++;
        }
        out.push({ t: 'num', v: sql.slice(start, i), s: start, e: i });
        continue;
      }
      if (RE_IDENT_START.test(c)) {
        i++;
        while (i < n && RE_IDENT.test(sql[i])) i++;
        out.push({ t: 'word', v: sql.slice(start, i), s: start, e: i });
        continue;
      }
      if (c === ':' && sql[i + 1] === ':') {
        i += 2;
        out.push({ t: 'cast', v: '::', s: start, e: i });
        continue;
      }
      if (c === ';') { i++; out.push({ t: 'semi', v: ';', s: start, e: i }); continue; }
      if ('()[],.'.indexOf(c) >= 0) {
        i++;
        out.push({ t: 'punct', v: c, s: start, e: i });
        continue;
      }
      if (OP_CHARS.indexOf(c) >= 0) {
        while (i < n && OP_CHARS.indexOf(sql[i]) >= 0) i++;
        out.push({ t: 'op', v: sql.slice(start, i), s: start, e: i });
        continue;
      }
      i++;      // anything else (a stray byte) is skipped, never fatal
    }
    return out;
  }

  /* ================= identifiers ================= */

  const unq = s => (s && s.length > 1 && s[0] === '"' && s.endsWith('"')
    ? s.slice(1, -1).replace(/""/g, '"') : s);
  // PostgreSQL folds unquoted identifiers to lower case and the plan prints
  // the folded form, so every comparison here folds too
  const fold = s => (s && s[0] === '"' ? unq(s) : String(s == null ? '' : s).toLowerCase());

  // words that terminate a FROM item list
  const FROM_END = new Set([
    'WHERE', 'GROUP', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'FETCH', 'WINDOW',
    'UNION', 'INTERSECT', 'EXCEPT', 'RETURNING', 'FOR', 'INTO', 'SET', 'ON',
    'USING', 'WITH', 'VALUES', 'SELECT', 'TABLESAMPLE', 'AS',
  ]);
  const JOIN_WORDS = new Set([
    'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'NATURAL', 'OUTER',
  ]);
  const REF_PREFIX = new Set(['ONLY', 'LATERAL']);
  const CMP_OPS = new Set(['=', '<', '>', '<=', '>=', '<>', '!=']);

  /* ================= scanner ================= */

  /**
   * scan(sql) -> {
   *   relations: [{ref, name, schema, alias, kind, depth, s, e}],
   *   ctes: [{name, s, e}],
   *   params: {count, max},
   *   predicateLiterals: n,          // literals used in comparisons
   *   casts: [{col, qualified, type, s, e}],   // casts written in the SQL
   *   forms: {notIn: [{s, e}], notExists: n, inSubquery: n},
   *   statements: n,
   * }
   */
  function scan(sql) {
    const text = String(sql == null ? '' : sql);
    const tk = lex(text);
    const relations = [];
    const seenSpan = new Set();
    const ctes = [];
    const casts = [];
    const forms = { notIn: [], notExists: 0, inSubquery: 0 };
    const params = new Set();
    let statements = tk.length ? 1 : 0;
    let predicateLiterals = 0;

    const W = i => (tk[i] && tk[i].t === 'word' ? tk[i].v.toUpperCase() : null);
    const isP = (i, v) => !!tk[i] && tk[i].t === 'punct' && tk[i].v === v;

    // parenthesis nesting depth of each token — a cheap stand-in for subquery
    // scope, enough to order candidates when an alias repeats
    const depths = new Array(tk.length);
    {
      let d = 0;
      for (let i = 0; i < tk.length; i++) {
        if (isP(i, ')')) d = Math.max(0, d - 1);
        depths[i] = d;
        if (isP(i, '(')) d++;
      }
    }

    const skipParens = i => {                 // tk[i] must be "("
      let d = 0;
      for (let k = i; k < tk.length; k++) {
        if (isP(k, '(')) d++;
        else if (isP(k, ')')) { d--; if (d === 0) return k + 1; }
      }
      return tk.length;
    };

    // one qualified name: a.b.c / "A"."b"
    const readName = i => {
      const parts = [];
      let k = i;
      for (;;) {
        const t = tk[k];
        if (!t || (t.t !== 'word' && t.t !== 'qid')) break;
        parts.push(t.v);
        k++;
        if (isP(k, '.')) { k++; continue; }
        break;
      }
      if (!parts.length) return null;
      return { parts, ref: parts.join('.'), s: tk[i].s, e: tk[k - 1].e, next: k };
    };

    // one FROM item; returns the index after it
    const readFromItem = (i, depth) => {
      let k = i;
      while (REF_PREFIX.has(W(k))) k++;
      let entry;
      if (isP(k, '(')) {
        // parenthesized source (subquery, VALUES, join group): its own FROM
        // items are found by the main sweep, only the wrapper alias is kept
        const after = skipParens(k);
        entry = {
          ref: null, name: null, schema: null, kind: 'subquery', depth,
          s: tk[k].s, e: tk[after - 1] ? tk[after - 1].e : tk[k].e,
        };
        k = after;
      } else {
        const nm = readName(k);
        if (!nm) return k + 1;
        k = nm.next;
        let kind = 'table';
        if (isP(k, '(')) { kind = 'function'; k = skipParens(k); }
        entry = {
          ref: nm.ref,
          name: fold(nm.parts[nm.parts.length - 1]),
          schema: nm.parts.length > 1 ? fold(nm.parts.slice(0, -1).join('.')) : null,
          kind, depth, s: nm.s, e: nm.e,
        };
      }
      if (W(k) === 'AS') k++;
      const aw = tk[k];
      const av = aw && (aw.t === 'word' || aw.t === 'qid') ? aw.v.toUpperCase() : null;
      if (aw && av !== null && !FROM_END.has(av) && !JOIN_WORDS.has(av)) {
        entry.alias = fold(aw.v);
        entry.e = aw.e;
        k++;
        if (isP(k, '(')) k = skipParens(k);      // t(col1, col2)
      } else {
        entry.alias = null;
      }
      // the sweep walks into parenthesized groups instead of jumping over
      // them, so the same item can be reached twice — keep the first
      const span = entry.s + ':' + entry.e;
      if (!seenSpan.has(span)) { seenSpan.add(span); relations.push(entry); }
      return k;
    };

    for (let i = 0; i < tk.length; i++) {
      const t = tk[i];
      if (t.t === 'param') { params.add(t.v); continue; }
      if (t.t === 'semi') { if (i < tk.length - 1) statements++; continue; }
      if (t.t === 'str' || t.t === 'num') {
        // only a literal on the far side of a comparison says anything about
        // how the statement was sent
        const prev = tk[i - 1];
        if (prev && ((prev.t === 'op' && CMP_OPS.has(prev.v))
            || (prev.t === 'word' && /^(LIKE|ILIKE|BETWEEN|IN)$/i.test(prev.v)))) {
          predicateLiterals++;
        }
        continue;
      }
      if (t.t === 'cast') {
        // "col::type": the shape that stops an index on the column from being
        // usable. Only a bare column reference is interesting.
        const prev = tk[i - 1];
        if (prev && (prev.t === 'word' || prev.t === 'qid')) {
          const type = readName(i + 1);
          const qualStart = isP(i - 2, '.') ? i - 3 : i - 1;
          const col = readName(Math.max(0, qualStart));
          if (type) {
            casts.push({
              col: fold(prev.v),
              qualified: col ? col.ref : prev.v,
              type: fold(type.parts[type.parts.length - 1]),
              s: (col || prev).s, e: type.e,
            });
          }
        }
        continue;
      }
      if (t.t !== 'word') continue;
      const w = t.v.toUpperCase();

      if (w === 'CAST' && isP(i + 1, '(')) {              // CAST(col AS type)
        const inner = readName(i + 2);
        if (inner && W(inner.next) === 'AS') {
          const type = readName(inner.next + 1);
          if (type) {
            casts.push({
              col: fold(inner.parts[inner.parts.length - 1]),
              qualified: inner.ref,
              type: fold(type.parts[type.parts.length - 1]),
              s: t.s, e: type.e,
            });
          }
        }
        continue;
      }
      if (w === 'WITH') {
        // WITH [RECURSIVE] name [(cols)] AS [NOT] [MATERIALIZED] ( ... ) [, ...]
        let k = i + 1;
        if (W(k) === 'RECURSIVE') k++;
        for (;;) {
          const nm = readName(k);
          if (!nm) break;
          k = nm.next;
          if (isP(k, '(')) k = skipParens(k);
          if (W(k) !== 'AS') break;
          k++;
          while (W(k) === 'NOT' || W(k) === 'MATERIALIZED') k++;
          if (!isP(k, '(')) break;
          const end = skipParens(k);
          ctes.push({
            name: fold(nm.parts[nm.parts.length - 1]),
            s: nm.s, e: tk[end - 1] ? tk[end - 1].e : nm.e,
          });
          k = end;
          if (isP(k, ',')) { k++; continue; }
          break;
        }
        continue;
      }
      if (w === 'NOT' && W(i + 1) === 'IN' && isP(i + 2, '(') && W(i + 3) === 'SELECT') {
        const end = skipParens(i + 2);
        forms.notIn.push({ s: t.s, e: tk[end - 1] ? tk[end - 1].e : t.e });
        continue;
      }
      if (w === 'NOT' && W(i + 1) === 'EXISTS') { forms.notExists++; continue; }
      if (w === 'IN' && isP(i + 1, '(') && W(i + 2) === 'SELECT') { forms.inSubquery++; continue; }

      // relation lists. "USING" is skipped on purpose: after a JOIN it
      // introduces a column list, and DELETE ... USING is rare enough that
      // guessing wrong would cost more than the miss.
      // "UPDATE" only starts one as a statement: in "FOR UPDATE SKIP LOCKED"
      // (or FOR NO KEY UPDATE) it is a locking clause, and reading a relation
      // there invents a table called "skip".
      const lockClause = w === 'UPDATE'
        && (W(i - 1) === 'FOR' || W(i - 2) === 'FOR' || W(i - 3) === 'FOR');
      const isList = (!lockClause && (w === 'FROM' || w === 'JOIN' || w === 'UPDATE'))
        || (w === 'INTO' && (W(i - 1) === 'INSERT' || W(i - 1) === 'MERGE'));
      if (!isList) continue;

      let k = i + 1;
      for (;;) {
        const nw = W(k);
        if (k >= tk.length) break;
        if (nw && FROM_END.has(nw) && !REF_PREFIX.has(nw)) break;
        if (nw && JOIN_WORDS.has(nw)) { k++; continue; }
        const before = k;
        k = readFromItem(k, depths[k] || 0);
        if (k <= before) k = before + 1;
        if (isP(k, ',')) { k++; continue; }
        const after = W(k);
        if (after && JOIN_WORDS.has(after)) { k++; continue; }
        break;
      }
      // deliberately no jump to k: the loop must still walk into the group so
      // that a subquery's own FROM items are seen (duplicates are filtered by
      // span above)
    }

    const nums = [...params].map(p => Number(p.slice(1)));
    return {
      relations,
      ctes,
      casts,
      forms,
      statements,
      predicateLiterals,
      params: { count: params.size, max: nums.length ? Math.max(...nums) : 0 },
      length: text.length,
    };
  }

  /* ================= binding to a plan ================= */

  // PostgreSQL aliases the children of a partitioned or inherited scan after
  // the parent: "orders o" becomes "orders_p2026_08 o_1". That is the server's
  // own construction and ties a child to one FROM item. A shared name prefix
  // is not: any two tables may be called orders_archive and orders_backup.
  const parentAlias = a => (a && /_\d+$/.test(a) ? a.replace(/_\d+$/, '') : null);

  // scans that carry a "relation" which is not a table: their name comes from
  // the query's own structure, so the reverse check must skip them
  const STRUCTURAL_SCAN = new Set([
    'CTE Scan', 'Subquery Scan', 'Function Scan', 'Table Function Scan',
    'Values Scan', 'WorkTable Scan', 'Named Tuplestore Scan',
  ]);

  /**
   * bind(sc, plan) -> {bound, reason, coverage, matched, sqlOnly, planOnly,
   *                    byAlias, byName, byCte}
   *
   * Establishes that the SQL and the plan describe the same statement, and
   * maps plan aliases onto the FROM items they came from. The policy is
   * fail-closed and runs in both directions: every relation the query names
   * must be read by the plan, and every table the plan reads must be named by
   * the query (or be a child of one). A plan explained against somebody
   * else's query is worse than a plan explained on its own.
   */
  function bind(sc, plan) {
    const nodes = plan.nodes || [];
    const planRels = [];
    for (const n of nodes) {
      if (n.spec || !n.relation) continue;
      const parts = String(n.relation).split('.');
      planRels.push({
        name: fold(parts[parts.length - 1]),
        schema: parts.length > 1 ? fold(parts.slice(0, -1).join('.')) : null,
        alias: n.alias ? fold(n.alias) : null,
        structural: STRUCTURAL_SCAN.has(n.nodeType || ''),
      });
    }

    // A schema is decisive only when both sides carry one: a TEXT plan prints
    // no schema at all, so requiring it there would refuse every text plan.
    const sameSchema = (a, b) => !a || !b || a === b;

    const cteNames = new Set(sc.ctes.map(c => c.name));
    const base = sc.relations.filter(r => r.kind === 'table' && r.name && !cteNames.has(r.name));
    // what the query names as a source: base tables plus its CTEs (the plan
    // reads those through a CTE Scan, so they carry a relation name too)
    const sources = [];
    const seen = new Set();
    for (const r of base) {
      const key = (r.schema ? r.schema + '.' : '') + r.name;
      if (seen.has(key)) continue;
      seen.add(key);
      sources.push({ name: r.name, schema: r.schema, alias: r.alias });
    }
    for (const c of sc.ctes) {
      if (seen.has(c.name)) continue;
      seen.add(c.name);
      sources.push({ name: c.name, schema: null, alias: null });
    }

    const isChild = (rel, src) => parentAlias(rel.alias) === (src.alias || src.name);
    const sameRel = (rel, src) => rel.name === src.name && sameSchema(src.schema, rel.schema);
    const inPlan = src => planRels.some(r => sameRel(r, src) || (!r.structural && isChild(r, src)));
    const explained = rel => sources.some(src => sameRel(rel, src) || isChild(rel, src));

    const matched = sources.filter(inPlan).map(s => s.name);
    const sqlOnly = sources.filter(s => !inPlan(s))
      .map(s => (s.schema ? s.schema + '.' : '') + s.name);
    const planOnly = [...new Set(planRels
      .filter(r => !r.structural && !explained(r))
      .map(r => (r.schema ? r.schema + '.' : '') + r.name))];
    const coverage = sources.length ? matched.length / sources.length : 0;

    // fail-closed: views expand, joins get eliminated and partitions replace
    // their parent — all plausible reasons for the two sides to differ, and
    // all indistinguishable from here from simply the wrong query
    let reason = null;
    if (!sources.length) reason = 'no-relations';
    else if (sc.statements > 1) reason = 'multi-statement';
    else if (sqlOnly.length) reason = 'partial';
    else if (planOnly.length) reason = 'plan-only';

    // alias -> FROM item, plus the CTE definitions
    const byAlias = new Map();
    for (const r of sc.relations) {
      const key = r.alias || r.name;
      if (key && !byAlias.has(key)) byAlias.set(key, r);
    }
    const byName = new Map();
    for (const r of base) if (!byName.has(r.name)) byName.set(r.name, r);
    const byCte = new Map();
    for (const c of sc.ctes) if (!byCte.has(c.name)) byCte.set(c.name, c);

    return {
      bound: reason === null, reason, coverage, matched, sqlOnly, planOnly,
      byAlias, byName, byCte,
    };
  }

  return { lex, scan, bind, fold, parentAlias };
}));
