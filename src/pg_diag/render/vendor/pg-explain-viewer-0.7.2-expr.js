/*
 * pgplan-expr.js — condition-expression parsing for pg-explain-viewer.
 *
 * Parses the predicate texts EXPLAIN prints (Index Cond / Filter /
 * Hash Cond / Sort Key / ...) into column references and comparison
 * segments. Two consumers:
 *   - the relations pane (which columns of which tables are used in what
 *     role, plus join edges between tables);
 *   - the index adviser (CREATE INDEX suggestions for the advisor rules).
 *
 * Pure JS, zero dependencies, UMD.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.PgPlanExpr = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ================= tokenizer ================= */

  // token: {t: type, v: text, pos}
  // types: str num qid word op punct cast dot param
  const RE_TOKEN = new RegExp(
    "'(?:[^']|'')*'"              // string literal
    + '|"[^"]+"'                  // quoted identifier
    + '|\\$\\d+'                  // $N parameter
    + '|::'                       // cast
    + '|-?\\d+(?:\\.\\d+)?'       // number
    + '|[a-zA-Z_][\\w$]*'         // word
    + '|[()\\[\\],]'              // punctuation
    + '|\\.'                      // qualification
    + '|[+\\-*/<>=~!@#%^&|?]+',   // operator
    'g');

  const KEYWORDS = new Set([
    'AND', 'OR', 'NOT', 'IS', 'NULL', 'TRUE', 'FALSE', 'ANY', 'ALL', 'SOME',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'BETWEEN', 'LIKE', 'ILIKE',
    'SIMILAR', 'TO', 'IN', 'EXISTS', 'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST',
    'ARRAY', 'ROW', 'DISTINCT', 'FROM', 'COLLATE', 'ESCAPE',
  ]);

  // words that continue a multi-word type name after ::cast
  const TYPE_TAIL = new Set([
    'without', 'with', 'time', 'zone', 'precision', 'varying', 'character', 'double',
  ]);

  const VOLATILE_FUNCS = new Set([
    'now', 'clock_timestamp', 'statement_timestamp', 'transaction_timestamp',
    'timeofday', 'random', 'gen_random_uuid', 'uuid_generate_v1',
    'uuid_generate_v4', 'nextval', 'currval', 'setval', 'txid_current',
  ]);

  const CMP_WORD_OPS = new Set(['LIKE', 'ILIKE', 'BETWEEN', 'IN', 'SIMILAR']);

  function tokenize(s) {
    const out = [];
    for (const m of s.matchAll(RE_TOKEN)) {
      const v = m[0];
      let t;
      if (v[0] === "'") t = 'str';
      else if (v[0] === '"') t = 'qid';
      else if (v[0] === '$') t = 'param';
      else if (v === '::') t = 'cast';
      else if (v === '.') t = 'dot';
      else if (/^-?\d/.test(v)) t = 'num';
      else if (/^[a-zA-Z_]/.test(v)) t = 'word';
      else if (/^[()\[\],]$/.test(v)) t = 'punct';
      else t = 'op';
      out.push({ t, v, pos: m.index });
    }

    // classify words: functions, types after ::, columns, keywords, params
    for (let i = 0; i < out.length; i++) {
      const tk = out[i];
      if (tk.t === 'param') continue;
      // (InitPlan N).colX / (SubPlan N) / (hashed SubPlan N) -> param
      if (tk.t === 'punct' && tk.v === '(') {
        let j = i + 1;
        if (out[j] && out[j].t === 'word' && out[j].v === 'hashed') j++;
        if (out[j] && out[j].t === 'word' && /^(InitPlan|SubPlan)$/.test(out[j].v)
            && out[j + 1] && out[j + 1].t === 'num'
            && out[j + 2] && out[j + 2].v === ')') {
          for (let k = i; k <= j + 2; k++) out[k].t = 'param';
          // trailing ".colN"
          if (out[j + 3] && out[j + 3].t === 'dot' && out[j + 4]) {
            out[j + 3].t = 'param'; out[j + 4].t = 'param';
          }
          i = j + 2;
          continue;
        }
      }
      if (tk.t !== 'word' && tk.t !== 'qid') continue;
      const up = tk.v.toUpperCase();
      if (tk.t === 'word' && KEYWORDS.has(up)) { tk.t = 'kw'; tk.v = up; continue; }
      const prev = out[i - 1], next = out[i + 1];
      if (prev && prev.t === 'cast') {
        tk.t = 'type';
        // multi-word (timestamp without time zone) and schema-qualified
        // (pagila.mpaa_rating) type names
        let j = i + 1;
        while (out[j]) {
          if (out[j].t === 'word' && TYPE_TAIL.has(out[j].v)) { out[j].t = 'type'; j++; }
          else if (out[j].t === 'dot' && out[j + 1]
              && (out[j + 1].t === 'word' || out[j + 1].t === 'qid')) {
            out[j].t = 'type'; out[j + 1].t = 'type'; j += 2;
          } else break;
        }
        i = j - 1;
        continue;
      }
      if (next && next.v === '(' && next.t === 'punct') { tk.t = 'func'; continue; }
      if (next && next.t === 'dot' && out[i + 2]
          && (out[i + 2].t === 'word' || out[i + 2].t === 'qid')) {
        tk.t = 'rel';
        out[i + 1].t = 'qual';
        out[i + 2].t = out[i + 2].t === 'qid' ? 'colq' : 'col';
        i += 2;
        continue;
      }
      if (prev && prev.t === 'qual') continue; // already claimed
      tk.t = tk.t === 'qid' ? 'colq' : 'col';
    }
    for (const tk of out) if (tk.t === 'colq') tk.t = 'col';
    return out;
  }

  // strip outer quotes AND undouble embedded ones: plan text prints the
  // identifier we"ird as "we""ird"
  const unq = v => (v.length > 1 && v[0] === '"' && v.endsWith('"')
    ? v.slice(1, -1).replace(/""/g, '"') : v);

  /* ================= structure ================= */

  // Extract column references: [{rel|null, col, pos}]
  function columnsOf(tokens) {
    const cols = [];
    for (let i = 0; i < tokens.length; i++) {
      const tk = tokens[i];
      if (tk.t === 'rel') {
        cols.push({ rel: unq(tk.v), col: unq(tokens[i + 2].v), pos: tk.pos });
        i += 2;
      } else if (tk.t === 'col') {
        cols.push({ rel: null, col: unq(tk.v), pos: tk.pos });
      }
    }
    return cols;
  }

  // Strip fully-enclosing parentheses layers from a token slice.
  function stripParens(tokens) {
    let tks = tokens;
    while (tks.length > 2 && tks[0].v === '(' && tks[tks.length - 1].v === ')') {
      let depth = 0, wraps = true;
      for (let i = 0; i < tks.length; i++) {
        if (tks[i].v === '(') depth++;
        else if (tks[i].v === ')') { depth--; if (depth === 0 && i < tks.length - 1) { wraps = false; break; } }
      }
      if (!wraps) break;
      tks = tks.slice(1, -1);
    }
    return tks;
  }

  // Split top-level AND segments (an OR at depth 0 keeps the whole thing as
  // one non-indexable segment). Returns [{tokens, text}].
  function splitAnd(tokens, text) {
    const tks = stripParens(tokens);
    const segs = [];
    let depth = 0, start = 0, hasOr = false;
    for (let i = 0; i < tks.length; i++) {
      const tk = tks[i];
      if (tk.v === '(' || tk.v === '[') depth++;
      else if (tk.v === ')' || tk.v === ']') depth--;
      else if (depth === 0 && tk.t === 'kw') {
        if (tk.v === 'AND') {
          segs.push(tks.slice(start, i));
          start = i + 1;
        } else if (tk.v === 'OR') hasOr = true;
      }
    }
    segs.push(tks.slice(start));
    if (hasOr) return { segments: [tks], or: true };
    return { segments: segs, or: false };
  }

  const segText = (seg, text) => {
    if (!seg.length) return '';
    const a = seg[0], b = seg[seg.length - 1];
    return text.slice(a.pos, b.pos + b.v.length);
  };

  // Analyze one AND-segment: find the top-level comparison operator and the
  // two sides.
  function analyzeSegment(seg, text) {
    // AND-parts arrive individually parenthesized: "(a = 1) AND (b > 5)"
    seg = stripParens(seg);
    let depth = 0;
    let opIdx = -1, opName = null;
    for (let i = 0; i < seg.length; i++) {
      const tk = seg[i];
      if (tk.v === '(' || tk.v === '[') depth++;
      else if (tk.v === ')' || tk.v === ']') depth--;
      else if (depth === 0 && opIdx === -1) {
        if (tk.t === 'op' && !/^[+\-*/^#]$|^\|\|$/.test(tk.v)) { opIdx = i; opName = tk.v; }
        else if (tk.t === 'kw' && CMP_WORD_OPS.has(tk.v)) { opIdx = i; opName = tk.v; }
        else if (tk.t === 'kw' && tk.v === 'IS') {
          opIdx = i;
          opName = 'IS';
          for (let j = i + 1; j < seg.length && seg[j].t === 'kw'; j++) opName += ' ' + seg[j].v;
        }
      }
    }
    const sideInfo = side => {
      const cols = columnsOf(side);
      let volatile = false, param = false;
      for (const tk of side) {
        if (tk.t === 'func' && VOLATILE_FUNCS.has(tk.v.toLowerCase())) volatile = true;
        if (tk.t === 'param') param = true;
      }
      return { tokens: side, cols, volatile, param, text: segText(side, text) };
    };
    if (opIdx === -1) {
      return { op: null, lhs: sideInfo(seg), rhs: null, text: segText(seg, text) };
    }
    return {
      op: opName,
      lhs: sideInfo(seg.slice(0, opIdx)),
      rhs: sideInfo(seg.slice(opIdx + 1).filter(tk => tk.t !== 'kw' || !/^(NOT|NULL|TRUE|FALSE)$/.test(tk.v) || opName !== 'IS')),
      text: segText(seg, text),
    };
  }

  function parse(text) {
    const tokens = tokenize(text);
    const { segments, or } = splitAnd(tokens, text);
    return {
      cols: columnsOf(tokens),
      or,
      segments: segments.map(seg => analyzeSegment(seg, text)),
    };
  }

  // Split a Sort Key / Group Key list on top-level commas.
  function splitList(text) {
    const tokens = tokenize(text);
    const parts = [];
    let depth = 0, start = 0;
    for (const tk of tokens) {
      if (tk.v === '(' || tk.v === '[') depth++;
      else if (tk.v === ')' || tk.v === ']') depth--;
      else if (tk.v === ',' && depth === 0) {
        parts.push(text.slice(start, tk.pos).trim());
        start = tk.pos + 1;
      }
    }
    parts.push(text.slice(start).trim());
    return parts.filter(Boolean);
  }

  /* ================= index adviser ================= */

  const LINEAR_OPS = new Set(['<', '<=', '=', '>=', '>', 'BETWEEN']);
  const PATTERN_OPS = new Set(['~~', '~~*', 'LIKE', 'ILIKE', '~', '~*']);
  const GIN_OPS = new Set(['@>', '<@', '&&', '?', '?|', '?&', '@?', '@@']);

  // Keywords PostgreSQL reserves (reserved + type_func_name categories):
  // they cannot appear as bare identifiers in DDL positions.
  // Keep in sync with the copy in pgplan.js.
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

  // SQL identifier quoting: simple lower-case non-reserved identifiers stay
  // bare, everything else is double-quoted with embedded quotes doubled.
  const RE_SIMPLE_IDENT = /^[a-z_][a-z0-9_$]*$/;
  const quoteIdent = name => (RE_SIMPLE_IDENT.test(name) && !SQL_RESERVED.has(String(name))
    ? name
    : '"' + String(name).replace(/"/g, '""') + '"');

  // Relation reference as printed in the plan: possibly schema-qualified,
  // each part possibly quoted (viz.t, "Weird", viz."We""ird"). Dots inside
  // quotes belong to the name; every part is re-quoted through quoteIdent
  // so the result is always safe SQL.
  function splitRelRef(ref) {
    const parts = [];
    let cur = '', i = 0;
    while (i < ref.length) {
      const ch = ref[i];
      if (ch === '"') {
        i++;
        while (i < ref.length) {
          if (ref[i] === '"') {
            if (ref[i + 1] === '"') { cur += '"'; i += 2; continue; }
            i++; break;
          }
          cur += ref[i++];
        }
      } else if (ch === '.') {
        parts.push(cur); cur = ''; i++;
      } else {
        cur += ch; i++;
      }
    }
    parts.push(cur);
    return parts;
  }

  const quoteRelRef = ref => splitRelRef(ref).map(quoteIdent).join('.');

  const fnv1a = s => {
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = (h * 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
  };

  const stripOrder = s => s.replace(/\s+(?:ASC|DESC)?\s*(?:NULLS\s+(?:FIRST|LAST))?\s*$/i, '');

  // Is this side a pure expression over the scanned relation?
  function localSide(side, relNames) {
    if (!side || side.param || side.volatile || !side.cols.length) return false;
    return side.cols.every(c => c.rel === null || relNames.has(c.rel));
  }

  // Strip alias/relation qualifiers (t.col -> col) via the tokenizer, so
  // string literals and identifiers that merely *contain* "t." are never
  // touched.
  function cleanExpr(text, relNames) {
    const tokens = tokenize(text);
    const cuts = []; // [start, end) spans of "rel." qualifiers to remove
    for (let i = 0; i + 1 < tokens.length; i++) {
      const tk = tokens[i];
      if (tk.t === 'rel' && tokens[i + 1].t === 'qual' && relNames.has(unq(tk.v))) {
        cuts.push([tk.pos, tokens[i + 1].pos + 1]);
      }
    }
    let s = '';
    let last = 0;
    for (const [a, b] of cuts) { s += text.slice(last, a); last = b; }
    s = (s + text.slice(last)).trim();
    // strip one level of enclosing parens
    while (/^\(.*\)$/.test(s)) {
      let depth = 0, wraps = true;
      for (let i = 0; i < s.length; i++) {
        if (s[i] === '(') depth++;
        else if (s[i] === ')') { depth--; if (depth === 0 && i < s.length - 1) { wraps = false; break; } }
      }
      if (!wraps) break;
      s = s.slice(1, -1).trim();
    }
    return s;
  }

  // bare column (possibly with a cast) → no extra parens needed
  const isPlainCol = s => /^[\w$]+(?:::[\w ]+)?$/.test(s) || /^"[^"]+"(?:::[\w ]+)?$/.test(s);

  // A fragment lifted from plan text may be embedded into generated DDL only
  // when the tokenizer consumes it completely (any stray byte — ';', '\',
  // control characters — fails the walk) and no operator token forms an SQL
  // comment marker. Everything else renders as a description, never as SQL.
  function isSafeFragment(s) {
    if (typeof s !== 'string' || !s.length || s.length > 160) return false;
    if (/[\u0000-\u001f\u007f]/.test(s)) return false;
    let last = 0;
    for (const m of s.matchAll(RE_TOKEN)) {
      if (s.slice(last, m.index).trim() !== '') return false;
      const v = m[0];
      last = m.index + v.length;
      if (v[0] === "'" || v[0] === '"') continue; // literals keep their quoting
      if (v.includes('--') || v.includes('/*') || v.includes('*/')) return false;
    }
    return s.slice(last).trim() === '';
  }

  // `written` (optional) names the columns the query text itself casts. A
  // cast on any other column was injected by the planner while matching
  // operator types (varchar -> text), and an index on the plain column serves
  // the predicate — proposing an expression index there only duplicates it.
  // Without the query text the two cases are indistinguishable in the plan,
  // so the cast is kept.
  const exprForIndex = (s, written) => {
    const noCast = s.replace(/::[\w ]+(\[\])?/g, '');
    if (/^[\w$]+$/.test(noCast) || /^"[^"]+"$/.test(noCast)) return noCast; // plain column
    if (written) {
      // "(col)::type" — keep the expression only when the query wrote exactly
      // this cast for this relation; anything else the planner injected while
      // matching operator types, and the plain column is what to index
      const m = /^\(?\s*([\w$]+|"[^"]+")\s*\)?::([\w ]+)$/.exec(s);
      if (m && !written.has(unq(m[1]).toLowerCase() + '::' + m[2].trim().toLowerCase())) {
        return m[1];
      }
    }
    return isPlainCol(s) || /^[a-z_][\w$]*\(.*\)$/i.test(s) ? s : '(' + s + ')';
  };

  /*
   * suggestIndexes({relation, alias, conds})
   *   -> [{rel, name, type, cols, where, def|null, comment, confidence}]
   *   conds: [{key: 'Index Cond'|'Recheck Cond'|'Filter'|'Join Cond'|'order-by', text}]
   * Builds up to two suggestions: a btree (equality cols → range col →
   * order-by cols [+ WHERE]) and, when array/jsonb operators are present,
   * a gin index.
   * confidence: 'exact'   — every condition was analyzed and covered;
   *             'partial' — some conditions were skipped, the DDL may not
   *                         cover everything;
   *             'unsafe'  — a plan-text fragment could not be verified as
   *                         safe SQL: def is null, only cols/where are
   *                         reported for display as text.
   */
  function suggestIndexes(spec) {
    const relation = spec.relation;
    if (!relation) return null;
    const relNames = new Set([unq(relation).replace(/^[^.]+\./, ''), unq(relation)]);
    if (spec.alias) relNames.add(unq(spec.alias));

    const eq = [], range = [], order = [], where = [], gin = [];
    let exact = true;
    let sawNonIndexKey = false; // something beyond an existing Index Cond

    for (const cond of spec.conds || []) {
      if (cond.key === 'order-by') {
        for (const part of splitList(cond.text)) {
          const clean = cleanExpr(stripOrder(part), relNames);
          const p = parse(clean);
          if (p.cols.length && p.cols.every(c => c.rel === null || relNames.has(c.rel))) {
            order.push(exprForIndex(clean, spec.writtenCasts));
            sawNonIndexKey = true;
          } else {
            exact = false;
          }
        }
        continue;
      }
      const parsed = parse(cond.text);
      if (parsed.or) { exact = false; continue; }
      for (const seg of parsed.segments) {
        const locL = localSide(seg.lhs, relNames);
        const locR = localSide(seg.rhs, relNames);
        const side = locL ? seg.lhs : locR ? seg.rhs : null;
        if (!side || !seg.op) {
          // bare boolean column?
          if (!seg.op && locL && seg.lhs.cols.length === 1) {
            where.push(cleanExpr(seg.text, relNames));
            if (cond.key !== 'Index Cond') sawNonIndexKey = true;
          } else exact = false;
          continue;
        }
        // both sides local (col op col on same table) — usable only in WHERE
        if (locL && locR) {
          where.push(cleanExpr(seg.text, relNames));
          if (cond.key !== 'Index Cond') sawNonIndexKey = true;
          continue;
        }
        const expr = exprForIndex(cleanExpr(side.text, relNames), spec.writtenCasts);
        const entry = { expr, op: seg.op, key: cond.key };
        if (cond.key !== 'Index Cond') sawNonIndexKey = true;
        if (seg.op === '=' || seg.op === 'IS NULL') eq.push(entry);
        else if (LINEAR_OPS.has(seg.op)) range.push(entry);
        else if (GIN_OPS.has(seg.op)) gin.push(entry);
        else if (PATTERN_OPS.has(seg.op)) range.push(Object.assign(entry, { pattern: true }));
        else if (seg.op === '<>' || seg.op === 'IS NOT NULL') {
          const w = cleanExpr(seg.text, relNames);
          if (w.length <= 100) where.push(w);
        } else exact = false;
      }
    }

    if (!sawNonIndexKey) return null; // an existing index already covers everything

    const uniq = arr => {
      const seen = new Set(), out = [];
      for (const e of arr) if (!seen.has(e.expr)) { seen.add(e.expr); out.push(e); }
      return out;
    };
    const eqU = uniq(eq);
    const rangeU = uniq(range).filter(e => !eqU.some(x => x.expr === e.expr));
    const orderU = [...new Set(order)]
      .filter(e => !eqU.some(x => x.expr === e) && !(rangeU[0] && rangeU[0].expr === e));
    const whereU = [...new Set(where)];

    const out = [];
    const mkDef = (type, cols, ops, whereList) => {
      const relParts = splitRelRef(relation);
      const relSql = quoteRelRef(relation);
      const colList = cols.join(', ');
      const w = whereList.length ? ' WHERE ' + whereList.join(' AND ') : '';
      const frmt = ` USING ${type} (${colList})${w}`;
      const base = relParts[relParts.length - 1];
      const idx = quoteIdent('~' + (base.length > 40 ? base.slice(0, 40) : base)
        + '-' + fnv1a(frmt));
      // safe-output contract: every plan-derived fragment must pass
      // isSafeFragment before it may appear in copyable SQL
      const safe = cols.every(isSafeFragment) && whereList.every(isSafeFragment);
      return {
        rel: relParts.join('.'),
        name: idx,
        type,
        cols,
        where: whereList,
        // unsafe: descriptive candidate only, never emitted as SQL
        def: safe ? `CREATE INDEX CONCURRENTLY ${idx}\n  ON ${relSql}${frmt};` : null,
        comment: ops.length ? ops.map(o => `${o.expr} (${o.op})`).join(', ') : null,
        confidence: !safe ? 'unsafe' : exact ? 'exact' : 'partial',
      };
    };

    // btree: eq cols, then one range col, then order-by tail. A range that
    // an existing Index Cond already serves makes a poor lead column, so a
    // range coming from a Filter goes first — that is the predicate the scan
    // is currently paying for.
    const rangeRank = rangeU.map((e, i) => [e.key === 'Index Cond' ? 1 : 0, i, e])
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(x => x[2]);
    const btreeOps = [...eqU, ...(rangeRank.length ? [rangeRank[0]] : [])];
    const btreeCols = btreeOps.map(e =>
      e.pattern ? e.expr + ' text_pattern_ops' : e.expr);
    btreeCols.push(...orderU);
    // further range predicates cannot act as search keys, but as trailing
    // columns they still let the filter be checked inside the index instead
    // of fetching the row first — the exact complaint INDEX_DISCARD makes
    const rangeTail = rangeRank.slice(1, 3).map(e => e.expr);
    for (const c of rangeTail) if (!btreeCols.includes(c)) btreeCols.push(c);
    if (btreeCols.length) {
      if (rangeU.length > 1) exact = false;
      // a candidate made only of columns the scan's own Index Cond already
      // uses would recreate the index that is right there in the plan
      const condOnly = new Set(
        [...eqU, ...rangeU].filter(e => e.key === 'Index Cond').map(e => e.expr));
      const redundant = spec.usesIndex && !orderU.length
        && btreeCols.every(c => condOnly.has(c));
      if (!redundant) out.push(mkDef('btree', btreeCols, btreeOps, whereU));
    }
    if (gin.length) {
      const ginU = uniq(gin);
      out.push(mkDef('gin', ginU.map(e => e.expr), ginU, []));
    }
    if (!out.length && whereU.length) return null; // nothing indexable
    return out.length ? out : null;
  }

  /* ================= schema (relations & joins) ================= */

  const ROLE_OF_KEY = {
    'Index Cond': 'cond', 'Recheck Cond': 'cond', 'TID Cond': 'cond',
    'Hash Cond': 'join', 'Merge Cond': 'join', 'Join Filter': 'join',
    'Filter': 'filter', 'One-Time Filter': 'filter', 'Conflict Filter': 'filter',
    'Order By': 'cond',
    'sort-key': 'sort', 'group-key': 'sort',
  };

  /*
   * buildSchema(plan) -> {rels: [...], joins: [...]}
   *   rel: {name, schema, aliases, nodes, indexes: [{name, nodes, cols}],
   *         cols: [{col, roles, nodes}]}
   *   join: {left: {rel, col}, right: {rel, col}, op, nodes}
   */
  function buildSchema(plan) {
    const nodes = plan.nodes;
    const rels = new Map();     // name -> rel entry
    const aliasMap = new Map(); // alias/name -> rel entry

    const relFor = n => {
      // Bitmap Index Scan: relation lives on the ancestor Bitmap Heap Scan
      if (n.nodeType === 'Bitmap Index Scan') {
        for (let p = n.parent; p != null; p = nodes[p].parent) {
          if (nodes[p].nodeType === 'Bitmap Heap Scan') return nodes[p];
        }
        return null;
      }
      return n.relation ? n : null;
    };

    // schema-qualified identity: same-name tables in different schemas are
    // distinct relations; quoted dots belong to the name (via splitRelRef)
    const identOf = holder => {
      const parts = splitRelRef(holder.relationRef || holder.relation);
      const name = parts[parts.length - 1];
      const schemaName = parts.length > 1 ? parts.slice(0, -1).join('.') : null;
      return { name, schemaName, key: (schemaName ? schemaName + '.' : '') + name };
    };

    // pass 1: relations, aliases, indexes
    for (const n of nodes) {
      if (n.spec) continue;
      const holder = relFor(n);
      if (!holder) continue;
      const { name, schemaName, key } = identOf(holder);
      let rel = rels.get(key);
      if (!rel) {
        rel = {
          name, schema: schemaName, aliases: new Set(), nodes: [],
          indexes: new Map(), cols: new Map(), virtual: /Scan/.test(holder.nodeType)
            && !/Seq Scan|Index|Bitmap|Tid|Sample/.test(holder.nodeType) ? holder.nodeType : null,
        };
        rels.set(key, rel);
      }
      rel.nodes.push(n.id);
      const alias = holder.alias ? unq(holder.alias) : null;
      if (alias) rel.aliases.add(alias);
      aliasMap.set(alias || key, rel);
      aliasMap.set(key, aliasMap.get(key) || rel);
      // bare-name fallback for unqualified column references (first wins)
      aliasMap.set(name, aliasMap.get(name) || rel);
      if (n.index) {
        const iname = unq(n.index);
        let idx = rel.indexes.get(iname);
        if (!idx) { idx = { name: iname, nodes: [], cols: new Set() }; rel.indexes.set(iname, idx); }
        idx.nodes.push(n.id);
      }
    }

    const addCol = (rel, col, role, nodeId) => {
      let c = rel.cols.get(col);
      if (!c) { c = { col, roles: new Set(), nodes: new Set() }; rel.cols.set(col, c); }
      c.roles.add(role);
      c.nodes.add(nodeId);
    };
    const resolve = (c, own) => {
      if (c.rel != null) return aliasMap.get(c.rel) || null;
      return own;
    };

    const joins = new Map();

    // pass 2: conditions & keys
    for (const n of nodes) {
      if (n.spec) continue;
      const holder = relFor(n);
      const own = holder
        ? (holder.alias ? aliasMap.get(unq(holder.alias)) : null)
          || rels.get(identOf(holder).key) || null
        : null;
      const conds = n.filters.map(f => ({ key: f.key, text: f.val }));
      if (n.sortKey) for (const part of splitList(n.sortKey)) conds.push({ key: 'sort-key', text: stripOrder(part) });
      if (n.groupKey) for (const part of splitList(n.groupKey)) conds.push({ key: 'group-key', text: part });

      for (const cond of conds) {
        const role = ROLE_OF_KEY[cond.key] || 'filter';
        let parsed;
        try { parsed = parse(cond.text); } catch (e) { continue; }
        for (const c of parsed.cols) {
          const rel = resolve(c, own);
          if (rel) addCol(rel, c.col, role, n.id);
          if (rel && role === 'cond' && n.index && cond.key === 'Index Cond') {
            const idx = rel.indexes.get(unq(n.index));
            if (idx) idx.cols.add(c.col);
          }
        }
        // join edges: comparison with columns of two different relations
        for (const seg of parsed.segments) {
          if (!seg.op || !seg.rhs) continue;
          const lcols = seg.lhs.cols.map(c => ({ c, rel: resolve(c, own) })).filter(x => x.rel);
          const rcols = seg.rhs.cols.map(c => ({ c, rel: resolve(c, own) })).filter(x => x.rel);
          if (lcols.length !== 1 || rcols.length !== 1) continue;
          const L = lcols[0], R = rcols[0];
          if (L.rel === R.rel) {
            // self-join: real only when the two sides use different
            // aliases; a same-alias comparison is an ordinary filter
            const qa = L.c.rel, qb = R.c.rel;
            if (!qa || !qb || qa === qb) continue;
          }
          const qn = r => (r.schema ? r.schema + '.' : '') + r.name;
          const [a, b] = qn(L.rel) <= qn(R.rel) ? [L, R] : [R, L];
          const key = qn(a.rel) + '.' + a.c.col + '|' + seg.op + '|' + qn(b.rel) + '.' + b.c.col;
          let j = joins.get(key);
          if (!j) {
            j = {
              left: { rel: qn(a.rel), col: a.c.col },
              right: { rel: qn(b.rel), col: b.c.col },
              op: seg.op, nodes: new Set(),
            };
            joins.set(key, j);
          }
          j.nodes.add(n.id);
          addCol(a.rel, a.c.col, 'join', n.id);
          addCol(b.rel, b.c.col, 'join', n.id);
        }
      }
    }

    return {
      rels: [...rels.values()].map(r => ({
        name: r.name,
        schema: r.schema,
        virtual: r.virtual,
        aliases: [...r.aliases],
        nodes: r.nodes,
        indexes: [...r.indexes.values()].map(i => ({
          name: i.name, nodes: i.nodes, cols: [...i.cols],
        })),
        cols: [...r.cols.values()].map(c => ({
          col: c.col, roles: [...c.roles], nodes: [...c.nodes],
        })),
      })),
      joins: [...joins.values()].map(j => ({
        left: j.left, right: j.right, op: j.op, nodes: [...j.nodes],
      })),
    };
  }

  return { tokenize, parse, splitList, suggestIndexes, buildSchema, quoteIdent, isSafeFragment };
}));
