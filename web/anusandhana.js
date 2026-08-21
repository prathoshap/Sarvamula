/* Anusandhāna — Sarvamūla scholarly analytics tab. Five views:
   Concept locator · Pramāṇa citations · Topic treemap · Word/collocation clouds · Co-occurrence net.
   Reuses globals from app.js: DB, q(), disp(), norm(), view(), status(). Data lazy-loaded from
   web/analytics/*.json (built by build_analytics.py). All rendering is inline SVG — offline, no libs. */
(function () {
  const A = {};                                   // loaded analytics cache
  const esc = s => (s || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const CATCOLOR = {veda:'#a8330d',brahmana:'#bd8a2d',aranyaka:'#7f9450',upanishad:'#4f6b8f',
                    sutra:'#7a1f0d',gita:'#c0632a',itihasa:'#8a5a2d',purana:'#6a4c93',
                    smriti:'#557a6b',stotra:'#b5794a',vyakarana:'#5a7a8a',shruti:'#8a7b3a',
                    tantra:'#8c5a7a',unattr:'#b0a08a',other:'#9a8f7d'};
  const TOPIC_CT = "content_type LIKE 'Heading%' OR content_type IN ('Subject','Title')";
  function csvDownload(name, rows) {
    const csv = rows.map(r => r.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8'}));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  }
  // a source's name in the reader's chosen script; `display` is the romanised fallback
  const srcName = s => (s && s.dev && s.dev[0] !== '(' && window.disp) ? disp(s.dev)
                     : (s && (s.display || s.dev)) || '';

  window.anuExportCite = function (dev) {
    const s = A.sources.find(x => x.dev === dev) || {display: dev};
    const rows = [['source', 'ref', 'quote', 'work', 'seq']];
    A.citations.filter(c => c.src === dev).forEach(c => rows.push([s.display, c.ref, c.q,
      (A.titles[c.work] ? A.titles[c.work].title : c.work), c.seq]));
    csvDownload('sarvamula-citations.csv', rows);
  };

  function load(cb) {
    if (A.loaded) return cb();
    status('loading analytics…');
    const names = ['citations','sources','concepts'];
    Promise.all(names.map(n => fetch('analytics/' + n + '.json').then(r => r.json())))
      .then(d => {
        names.forEach((n, i) => A[n] = d[i]);
        A.titles = Object.fromEntries(q("SELECT slug,title,n_blocks FROM works").map(r => [r.slug, r]));
        A.loaded = true; status(''); cb();
      }).catch(e => status('analytics load error: ' + e));
  }

  const VIEWS = [['concept','अन्वेषण','Concept'],['cite','प्रमाण','Citations']];
  let cur = 'concept', arg = '';

  window.renderAnu = function (sub, a) {
    load(() => {
      cur = sub || 'concept'; arg = a || '';
      const nav = `<div class="anav">` + VIEWS.map(([k, dv, en]) =>
        `<a class="atab${k === cur ? ' on' : ''}" href="#/anu/${k}">${disp(dv)} · ${en}</a>`).join('') + `</div>`;
      if (cur !== 'concept' && cur !== 'cite') cur = 'concept';
      const body = ({concept:viewConcept,cite:viewCite}[cur])();
      view().innerHTML = `<div class="anu">${nav}<div id="anubody">${body}</div></div>`;
      if (cur === 'concept') wireConcept();
      if (cur === 'cite' && arg === 'net') drawCiteNet();
      window.scrollTo(0, 0);
    });
  };

  /* ---------------- Pillar 1: CONCEPT LOCATOR ---------------- */
  function viewConcept() {
    const chips = A.concepts.map(c =>
      `<button class="chip" data-cid="${c.id}" title="${esc(c.gloss)}">${disp(c.dev)}<span>${esc(c.iast)}</span></button>`).join('');
    return `<div class="lead"><b>Concept locator</b> — where all does Madhva discuss a concept, across the 38 works?
        Editorial-topic hits (precise) + surface text hits (stem-based). <span class="muted">Seeded concepts are curated; free text also works.</span></div>
      <input id="cq" class="cinput" placeholder="concept or any word — e.g. तारतम्य, मोक्ष, bheda…">
      <div class="chips">${chips}</div>
      <div id="cres"></div>`;
  }
  function wireConcept() {
    const run = () => locate(document.getElementById('cq').value.trim());
    document.getElementById('cq').addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
    document.querySelectorAll('.chip').forEach(b => b.onclick = () => {
      const c = A.concepts.find(x => x.id === b.dataset.cid);
      document.getElementById('cq').value = c.dev; locate(c.dev, c);
    });
    if (arg) { document.getElementById('cq').value = arg; locate(arg); }
  }
  const LCAP = 3000, LPAGE = 25;
  let locState = null, locScope = '';
  window.anuLocScope = function (scope) { locScope = scope; if (locState) locate(locState.term, locState.concept); };
  const wtitle = w => A.titles[w] ? A.titles[w].title : w;
  const refstr = h => [h.skandha, h.adhyaya, h.verse].filter(x => x != null).join('.');
  // Build the WHERE for a concept. Three shapes, in order of precedence:
  //
  //   all: [[a,b],[c]]   →  (skel~a OR skel~b) AND (skel~c)      groups AND'd, alternatives OR'd
  //   not: [x,y]         →  AND skel NOT LIKE x AND skel NOT LIKE y
  //   stems: [a,b]       →  (skel~a OR skel~b)                   the original flat OR
  //
  // `all` exists because a doctrinal concept is rarely one word. "Glory of the Lord's feet" is
  // (पाद OR चरण OR पदाम्बुज) AND (महिम OR माहात्म्य): a flat OR on पाद returns 3,375 entries, most
  // of them section headings (प्रथमः पादः), while requiring the words adjacent finds nothing.
  // `not` removes exactly that noise, which no amount of synonym listing can.
  function conceptWhere(concept, freeStems) {
    const cl = [], args = [];
    const groups = (concept && concept.all && concept.all.length) ? concept.all
                 : (concept && concept.stems && concept.stems.length) ? [concept.stems]
                 : (freeStems || []).map(s => [s]);          // free text: every word must appear
    for (const g of groups) {
      const alts = (Array.isArray(g) ? g : [g]).filter(Boolean);
      if (!alts.length) continue;
      cl.push('(' + alts.map(() => 'text_skel LIKE ?').join(' OR ') + ')');
      for (const a of alts) args.push('%' + norm(a) + '%');
    }
    for (const x of ((concept && concept.not) || [])) {
      cl.push('text_skel NOT LIKE ?'); args.push('%' + norm(x) + '%');
    }
    return cl.length ? {where: cl.join(' AND '), args} : null;
  }
  function locate(term, concept) {
    if (!term) return;
    if (!concept) concept = A.concepts.find(c => c.terms.includes(term) || c.dev === term);
    // Free text is split into WORDS and AND'd, as the main search box does. As one substring it
    // demanded the words adjacent in order: "pada mahima" became '%pada mahim%' and matched
    // nothing, though 57 entries carry both words.
    const freeStems = concept ? [] : norm(term).split(' ').filter(Boolean);
    const stems = concept ? (concept.stems && concept.stems.length ? concept.stems
                             : [].concat(...(concept.all || []))) : freeStems;
    const topics = concept ? concept.topics
                 : (/[ऀ-ॿ]/.test(term) ? term.trim().split(/\s+/).filter(Boolean) : []);
    const W = conceptWhere(concept, freeStems);
    if (!W && !topics.length) return;
    const tw = W ? W.where : '0', args = W ? W.args : [];
    // Support both grantha-wise and prasthana-group search
    let sc = '', scA = [];
    if (locScope) {
      if (locScope.startsWith('prasthana:')) {
        const prasIdx = parseInt(locScope.split(':')[1]);
        const prasWorks = window.getPrasthanaWorks ? window.getPrasthanaWorks(prasIdx) : [];
        if (prasWorks && prasWorks.length > 0) {
          const placeholders = prasWorks.map(() => '?').join(',');
          sc = ` AND work IN (${placeholders})`;
          scA = prasWorks;
        }
      } else {
        sc = ' AND work=?';
        scA = [locScope];
      }
    }
    const byWork = q(`SELECT work, COUNT(*) c, MIN(seq) fs FROM entries WHERE (${tw})${sc} GROUP BY work`, [...args, ...scA]).sort((a, b) => b.c - a.c);
    const total = byWork.reduce((s, r) => s + r.c, 0);
    const loci = q(`SELECT work,seq,skandha,adhyaya,verse,text_dev FROM entries WHERE (${tw})${sc} ORDER BY work,seq LIMIT ${LCAP}`, [...args, ...scA]);
    A.lastLoci = loci;
    let topicHits = [];
    if (topics.length) {
      // A CONCEPT's topics are alternatives (OR). A free-text phrase is one string here, so its
      // words are AND'd instead — otherwise 'पाद महिमा' asked the editorial header to contain
      // that exact adjacent pair and matched nothing.
      const twh = topics.map(() => 'text_dev LIKE ?').join(concept ? ' OR ' : ' AND ');
      topicHits = q(`SELECT work,seq,text_dev FROM entries WHERE (${TOPIC_CT}) AND (${twh})${sc} LIMIT 80`, [...topics.map(t => '%' + t + '%'), ...scA]);
    }
    // Concept → Pramāṇa: attributed citations in/adjacent to the concept's loci blocks
    const seqset = new Set(); loci.forEach(h => { for (let d = -1; d <= 1; d++) seqset.add(h.work + '|' + (h.seq + d)); });
    const pram = {}; A.citations.forEach(c => { if (c.src[0] !== '(' && seqset.has(c.work + '|' + c.seq)) pram[c.src] = (pram[c.src] || 0) + 1; });
    const pramTop = Object.entries(pram).sort((a, b) => b[1] - a[1]).slice(0, 14);
    // Devanāgarī term to highlight in the target block (concept's own form, or a Devanāgarī query)
    const hlterm = concept ? concept.dev : (/[ऀ-ॿ]/.test(term) ? term : '');
    locState = {term, concept, stems, byWork, total, loci, topicHits, pramTop, hlterm, page: 0};
    renderLoc();
  }
  function renderLoc() {
    const S = locState, max = Math.max(1, ...S.byWork.map(r => r.c));
    const gloss = S.concept ? `<span class="muted"> — ${esc(S.concept.iast)}: ${esc(S.concept.gloss)}</span>` : '';
    const hlsuf = S.hlterm ? '/' + encodeURIComponent(S.hlterm) : '';
    const heat = S.byWork.map(r => `<a class="hrow" href="#/b/${r.work}/${r.fs}${hlsuf}" onclick="anuWalk('${r.work}')"><span class="hn">${esc(wtitle(r.work))}</span>
        <span class="hbar"><i style="width:${Math.round(100*r.c/max)}%"></i></span><span class="hc">${r.c}</span></a>`).join('');
    const pmax = S.pramTop.length ? S.pramTop[0][1] : 1;
    const pram = S.pramTop.map(([dev, c]) => { const s = A.sources.find(x => x.dev === dev) || {display: dev, category: 'other'};
      return `<a class="hrow" href="#/anu/cite/${encodeURIComponent(dev)}"><span class="hn"><i class="dot" style="background:${CATCOLOR[s.category]||CATCOLOR.other}"></i>${esc(srcName(s))}</span>
        <span class="hbar"><i style="width:${Math.round(100*c/pmax)}%;background:${CATCOLOR[s.category]||CATCOLOR.other}"></i></span><span class="hc">${c}</span></a>`; }).join('');
    const pages = Math.max(1, Math.ceil(S.loci.length / LPAGE)), pageLoci = S.loci.slice(S.page*LPAGE, (S.page+1)*LPAGE);
    const snip = h => `<a class="v hit" href="#/b/${h.work}/${h.seq}${hlsuf}" onclick="anuWalk('${h.work}')"><div class="ref">${esc(wtitle(h.work))}${refstr(h)?' '+refstr(h):''}</div><div class="body">${hl(h.text_dev, S.stems)}</div></a>`;
    const pager = pages > 1 ? `<div class="pager"><button ${S.page<=0?'disabled':''} onclick="anuLocGo(-1)">‹ Prev</button><span>${S.page+1} / ${pages}</span><button ${S.page>=pages-1?'disabled':''} onclick="anuLocGo(1)">Next ›</button></div>` : '';
    const cap = S.loci.length >= LCAP ? ` (first ${LCAP})` : '';
    document.getElementById('cres').innerHTML = `
      <div class="cstat">${S.total} text loci in ${S.byWork.length} work${S.byWork.length!==1?'s':''}${gloss}
        ${typeof scopeSelect==='function'?scopeSelect('c',locScope,'anuLocScope'):''}
        <button class="xbtn" onclick="anuExportConcept()">⤓ Export CSV</button></div>
      <div class="cgrid">
        <div><div class="chd">Distribution across works</div>${heat || '<div class="muted">no loci</div>'}
          ${S.pramTop.length ? `<div class="chd">Pramāṇas cited here</div>${pram}` : ''}</div>
        <div>
          ${S.topicHits.length ? `<div class="chd">Editorial topics (${S.topicHits.length}${S.topicHits.length===80?'+':''})</div>` +
            S.topicHits.map(t => `<a class="tpc" href="#/b/${t.work}/${t.seq}">${disp(t.text_dev)}<span>${esc(wtitle(t.work))}</span></a>`).join('') : ''}
          <div class="chd">Text loci${cap} — ${S.total?S.page*LPAGE+1:0}–${Math.min(S.loci.length,(S.page+1)*LPAGE)} of ${S.loci.length}</div>
          ${pager}${pageLoci.map(snip).join('')}${pageLoci.length>6?pager:''}
        </div>
      </div>`;
  }
  window.anuLocGo = function (d) { if (!locState) return; const mx = Math.ceil(locState.loci.length/LPAGE);
    locState.page = Math.max(0, Math.min(locState.page + d, mx - 1)); renderLoc(); document.getElementById('cq').scrollIntoView({block:'start'}); };
  // start an occurrence-walk of a work's loci — the reader shows a Prev/Next bar (app.js occWalk)
  window.anuWalk = function (work) { if (!locState || !locState.stems.length) return;
    const tw = locState.stems.map(() => 'text_skel LIKE ?').join(' OR ');
    const seqs = q(`SELECT seq FROM entries WHERE work=? AND (${tw}) ORDER BY seq`,
                   [work, ...locState.stems.map(s => '%' + s + '%')]).map(r => r.seq);
    window.occWalk = {work, seqs, term: locState.hlterm}; };
  window.anuExportConcept = function () { if (!locState) return;
    const rows = [['work','ref','seq','text']];
    locState.loci.forEach(h => rows.push([wtitle(h.work), refstr(h), h.seq, (h.text_dev||'').replace(/\s+/g,' ')]));
    csvDownload('sarvamula-' + ((locState.concept && locState.concept.id) || 'concept') + '-loci.csv', rows); };

  /* ---------------- Pillar 2: CITATIONS ---------------- */
  function viewCite() {
    if (arg === 'net') return `<div class="lead"><b>Citation network</b> — works ↔ pramāṇa sources (edge = citations). <a href="#/anu/cite">← ranking</a></div><div id="anet2"></div>`;
    const attributed = A.sources.filter(s => s.category !== 'unattr' && s.dev !== '(other)');
    const max = attributed.length ? attributed[0].count : 1;
    const bar = s => `<a class="hrow" href="#/anu/cite/${encodeURIComponent(s.dev)}">
        <span class="hn" title="${esc(s.category)}"><i class="dot" style="background:${CATCOLOR[s.category]||CATCOLOR.other}"></i>${esc(srcName(s))}</span>
        <span class="hbar"><i style="width:${Math.round(100*s.count/max)}%;background:${CATCOLOR[s.category]||CATCOLOR.other}"></i></span>
        <span class="hc">${s.count}</span></a>`;
    const CATNAME = {veda:'Veda-saṃhitā',shruti:'Śruti — named recensions',brahmana:'Brāhmaṇa',
      aranyaka:'Āraṇyaka',upanishad:'Upaniṣad',sutra:'Sūtra',gita:'Gītā',itihasa:'Itihāsa',
      purana:'Purāṇa',tantra:'Tantra / Pāñcarātra',smriti:'Smṛti',vyakarana:'Vyākaraṇa',stotra:'Stotra',other:'Other'};
    const CATORDER = ['veda','shruti','brahmana','aranyaka','upanishad','sutra','gita','itihasa','purana','tantra','smriti','vyakarana','stotra','other'];
    const grp = {}; attributed.forEach(s => (grp[s.category] = grp[s.category] || []).push(s));
    const bars = CATORDER.filter(c => grp[c]).map(c =>
      `<div class="catlabel"><i class="dot" style="background:${CATCOLOR[c]||CATCOLOR.other}"></i>${CATNAME[c]||c}<span>${grp[c].length}</span></div>` +
      grp[c].sort((a, b) => b.count - a.count).map(bar).join('')).join('');
    const un = A.sources.find(s => s.category === 'unattr');
    const unrow = un ? `<div class="chd">Untagged</div><a class="hrow" href="#/anu/cite/${encodeURIComponent(un.dev)}">
        <span class="hn"><i class="dot" style="background:${CATCOLOR.unattr}"></i>${esc(srcName(un))}</span>
        <span class="hbar"><i style="width:100%;background:${CATCOLOR.unattr};opacity:.5"></i></span>
        <span class="hc">${un.count}</span></a>` : '';
    const drill = arg ? citeDrill(arg) : '<div class="muted" style="padding:.5rem">Click a source to see every citation (with quote &amp; ref) and export.</div>';
    return `<div class="lead"><b>Pramāṇa citations</b> — ${A.citations.length} citation instances: kutra-tagged sources (with ref) + inline “…” quotations.
        In a drill, <span style="color:var(--gold);font-weight:700">†</span> = read from Madhva’s prose (इति …); <span style="color:var(--gold);font-weight:700">‡</span> = inferred from the block’s sole tagged source. <a href="#/anu/cite/net">view as network →</a></div>
      <div class="cgrid"><div><div class="chd">Sources by citation count</div>${bars}${unrow}</div><div id="cdrill">${drill}</div></div>`;
  }
  function citeDrill(dev) {
    const s = A.sources.find(x => x.dev === dev) || {display: dev};
    const all = A.citations.filter(c => c.src === dev), rows = all.slice(0, 400);
    const byWork = {}; all.forEach(c => (byWork[c.work] = (byWork[c.work] || 0) + 1));
    const wtag = Object.entries(byWork).sort((a,b)=>b[1]-a[1]).map(([w,c]) =>
      `<span class="wtag">${esc(A.titles[w]?A.titles[w].title:w)} ·${c}</span>`).join('');
    return `<div class="chd">${esc(srcName(s))} — ${all.length} citations
        <button class="xbtn" onclick="anuExportCite('${dev.replace(/'/g,"\\'")}')">⤓ CSV</button></div>
      <div class="wtags">${wtag}</div>` +
      rows.map(c => `<a class="citerow" href="#/b/${c.work}/${c.seq}${c.q ? '/' + encodeURIComponent(c.q) : ''}"><span class="cref">${esc(c.ref) || (c.q ? '“…”' : '—')}</span>
        <span class="cq">${c.q ? esc(disp(c.q)) : ''}${c.via === 'inline' ? '<span class="viatag" title="read from Madhva’s prose (इति …)">†</span>' : c.via === 'block' ? '<span class="viatag" title="inferred from this block’s sole kutra-tagged source">‡</span>' : ''}</span>
        <span class="muted">${esc(A.titles[c.work]?A.titles[c.work].title:c.work)}</span></a>`).join('') +
      (all.length > 400 ? `<div class="muted" style="padding:.5rem">showing 400 of ${all.length} — export CSV for all</div>` : '');
  }

  /* ---------------- Pillar 3: TOPIC TREEMAP ---------------- */
  function firstWorkWithTopics() { return Object.keys(A.topics).sort((a,b)=>A.topics[b].length-A.topics[a].length)[0]; }
  function viewTopic() {
    const opts = Object.keys(A.topics).sort((a,b)=>A.topics[b].length-A.topics[a].length)
      .map(w => `<option value="${w}"${w===(arg||firstWorkWithTopics())?' selected':''}>${esc(A.titles[w]?A.titles[w].title:w)} (${A.topics[w].length})</option>`).join('');
    return `<div class="lead"><b>Topic map</b> — the editorial topic hierarchy; tile size = span, click to open.</div>
      <select id="twork" class="cinput" style="max-width:340px">${opts}</select>
      <div id="tmap"></div>`;
  }
  function drawTreemap(work) {
    const sel = document.getElementById('twork'); if (sel) sel.onchange = () => { location.hash = '#/anu/topic/' + sel.value; };
    const nodes = (A.topics[work] || []).filter(n => n.w >= 2)   // drop pure section-divider headings
      .sort((a, b) => b.w - a.w).slice(0, 180);                  // largest sections, legible density
    const host = document.getElementById('tmap'); if (!host) return;
    const W = host.clientWidth || 900, H = 560;
    const rects = squarify(nodes.map(n => ({v: Math.max(1, n.w), n})), 0, 0, W, H);
    const lvlc = ['#7a1f0d','#a8330d','#c0632a','#bd8a2d'];
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="tmsvg" width="100%">` + rects.map(r => {
      const n = r.it, fs = Math.max(9, Math.min(16, r.w/8, r.h/2));
      const show = r.w > 34 && r.h > 14;
      return `<a href="#/b/${work}/${n.seq}"><rect x="${r.x+1}" y="${r.y+1}" width="${Math.max(0,r.w-2)}" height="${Math.max(0,r.h-2)}"
        rx="3" fill="${lvlc[Math.min(n.lvl,3)]}" opacity="${0.9-0.13*Math.min(n.lvl,3)}"><title>${esc(disp(n.t))} · ${n.w}</title></rect>
        ${show?`<text x="${r.x+5}" y="${r.y+14}" font-size="${fs}" fill="#fff" clip-path="inset(0 0 0 0)">${esc(disp(n.t)).slice(0,Math.floor(r.w/(fs*0.6)))}</text>`:''}</a>`;
    }).join('') + `</svg>`;
  }
  function squarify(data, x, y, w, h) {           // squarified treemap (Bruls et al.)
    const out = [], tot = data.reduce((s, d) => s + d.v, 0);
    if (tot <= 0 || w <= 0 || h <= 0) return out;
    const scale = (w * h) / tot;
    const items = data.map(d => ({a: d.v * scale, it: d.n})).sort((p, q2) => q2.a - p.a);
    let rx = x, ry = y, rw = w, rh = h, row = [];
    const worst = (r, len) => { const s = r.reduce((a, b) => a + b.a, 0);
      let mx = 0, mn = Infinity; r.forEach(o => { mx = Math.max(mx, o.a); mn = Math.min(mn, o.a); });
      return Math.max((len * len * mx) / (s * s), (s * s) / (len * len * mn)); };
    const lay = () => { const s = row.reduce((a, b) => a + b.a, 0);
      if (rw >= rh) { const dw = s / rh; let cy = ry; row.forEach(o => { const ih = o.a / dw; out.push({x: rx, y: cy, w: dw, h: ih, it: o.it}); cy += ih; }); rx += dw; rw -= dw; }
      else { const dh = s / rw; let cx = rx; row.forEach(o => { const iw = o.a / dh; out.push({x: cx, y: ry, w: iw, h: dh, it: o.it}); cx += iw; }); ry += dh; rh -= dh; }
      row = []; };
    items.forEach(o => { const len = Math.min(rw, rh);
      if (!row.length) { row.push(o); return; }
      if (worst(row, len) >= worst(row.concat(o), len)) row.push(o);
      else { lay(); row.push(o); } });
    if (row.length) lay();
    return out;
  }

  /* ---------------- Pillar 4: WORD & COLLOCATION CLOUDS ---------------- */
  function viewWord() {
    const opts = `<option value="">Whole corpus</option>` + Object.keys(A.wordfreq.byWork)
      .sort((a,b)=>(A.titles[a]?0:1)-(A.titles[b]?0:1)||(A.titles[a]&&A.titles[b]?A.titles[a].title.localeCompare(A.titles[b].title):0))
      .map(w=>`<option value="${w}"${w===arg?' selected':''}>${esc(A.titles[w]?A.titles[w].title:w)}</option>`).join('');
    const coll = A.wordfreq.collocations.slice(0, 60).map(c =>
      `<a class="collo" href="#/anu/word/${encodeURIComponent(c[0].split(' ')[0])}"><span>${disp(c[0])}</span><i>${c[1]}</i></a>`).join('');
    return `<div class="lead"><b>Word & phrase frequency</b> <span class="muted">(surface forms — inflected forms count separately; avyayas removed)</span></div>
      <select id="wwork" class="cinput" style="max-width:340px">${opts}</select>
      <div id="wcloud" class="wcloud"></div>
      <div class="chd">Frequent collocations (log-likelihood ranked)</div><div class="collos">${coll}</div>`;
  }
  function drawCloud() {
    const sel = document.getElementById('wwork'); if (sel) sel.onchange = () => location.hash = '#/anu/word' + (sel.value?'/'+sel.value:'');
    const list = (arg && A.wordfreq.byWork[arg] ? A.wordfreq.byWork[arg] : A.wordfreq.corpus).slice(0, 90);
    const host = document.getElementById('wcloud'); if (!host) return;
    const max = list[0][1], min = list[list.length-1][1];
    host.innerHTML = list.map(([w, c]) => {
      const sz = 12 + 30 * (Math.sqrt(c) - Math.sqrt(min)) / (Math.sqrt(max) - Math.sqrt(min) || 1);
      const op = 0.5 + 0.5 * (c - min) / (max - min || 1);
      return `<a class="cw" style="font-size:${sz.toFixed(1)}px;opacity:${op.toFixed(2)}" title="${c}"
        href="#/anu/concept/${encodeURIComponent(w)}">${disp(w)}</a>`;
    }).join(' ');
  }

  /* ---------------- Pillar 5: CO-OCCURRENCE NETWORK ---------------- */
  function viewNet() {
    return `<div class="lead"><b>Word co-occurrence</b> <span class="muted">(surface forms sharing a verse/block; drag-free force layout)</span></div>
      <div id="anet"></div>`;
  }
  function drawNetwork(data, elId, hrefFn) { forceGraph(data, elId, hrefFn); }
  function drawCiteNet() {
    // bipartite works ↔ sources; nodes = [label, weight, color, href, isDeva]
    const bySrc = {}; A.citations.forEach(c => { if (c.src === '(other)') return;
      const k = c.src + '|' + c.work; bySrc[k] = (bySrc[k] || 0) + 1; });
    const nodes = [], nidx = {}, add = (id, label, w, color, href, deva) => {
      if (nidx[id] == null) { nidx[id] = nodes.length; nodes.push([label, w, color, href, deva]); }
      else nodes[nidx[id]][1] += w; };
    const edges = [];
    Object.entries(bySrc).forEach(([k, c]) => { const [src, work] = k.split('|');
      const sMeta = A.sources.find(s => s.dev === src) || {display: src, category: 'other'};
      add('s:' + src, srcName(sMeta), c, CATCOLOR[sMeta.category] || CATCOLOR.other, '#/anu/cite/' + encodeURIComponent(src), false);
      add('w:' + work, A.titles[work] ? A.titles[work].title : work, c, '#2a2018', '#/w/' + work, false);
      edges.push([nidx['s:' + src], nidx['w:' + work], c]); });
    forceGraph({nodes, edges: edges.map(e => [e[0], e[1], e[2]]), indexed: true}, 'anet2');
  }
  // force-directed layout → static SVG. data.nodes: [label,weight,color?,href?,deva?].
  // edges reference node labels, or indices when data.indexed.
  function forceGraph(data, elId, hrefFn) {
    const box = document.getElementById(elId); if (!box) return;
    const W = box.clientWidth || 900, H = 620;
    const idx = {}; data.nodes.forEach((n, i) => idx[n[0]] = i);
    const edges = data.indexed ? data.edges
      : data.edges.filter(e => idx[e[0]] != null && idx[e[1]] != null).map(e => [idx[e[0]], idx[e[1]], e[2]]);
    const maxc = Math.max(...data.nodes.map(n => n[1]), 1);
    const P = data.nodes.map((n, i) => ({x: Math.cos(i*2.399)*(30+(i%13)*4), y: Math.sin(i*2.399)*(30+(i%11)*4), vx:0, vy:0, n}));
    const K = 0.09, REP = 1500, SPR = 0.02;             // strong gravity, gentle repulsion
    for (let it = 0; it < 300; it++) {
      const cool = Math.max(0.1, 1 - it/320);            // anneal → settle, no edge-clamp ring
      for (let i = 0; i < P.length; i++) { let fx = 0, fy = 0;
        for (let j = 0; j < P.length; j++) { if (i === j) continue; const dx = P[i].x-P[j].x, dy = P[i].y-P[j].y, d2 = dx*dx+dy*dy+0.1, f = REP/d2; fx += dx*f; fy += dy*f; }
        fx += (0 - P[i].x)*K; fy += (0 - P[i].y)*K;      // gravity to origin (scaled to fit later)
        P[i].vx = (P[i].vx+fx)*0.85; P[i].vy = (P[i].vy+fy)*0.85; }
      edges.forEach(e => { const a = P[e[0]], b = P[e[1]], dx = b.x-a.x, dy = b.y-a.y; a.vx += dx*SPR; a.vy += dy*SPR; b.vx -= dx*SPR; b.vy -= dy*SPR; });
      P.forEach(p => { p.x += p.vx*cool; p.y += p.vy*cool; });
    }
    // fit the settled layout into the viewport (no edge-sticking)
    const pad = 60, xs = P.map(p => p.x), ys = P.map(p => p.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const sx = (W - 2*pad) / (x1 - x0 || 1), sy = (H - 2*pad) / (y1 - y0 || 1), s = Math.min(sx, sy);
    P.forEach(p => { p.x = pad + (p.x - x0) * s + (W - 2*pad - (x1 - x0)*s)/2; p.y = pad + (p.y - y0) * s + (H - 2*pad - (y1 - y0)*s)/2; });
    const emax = Math.max(...edges.map(e => e[2]), 1);
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" class="netsvg">
      ${edges.map(e => { const a = P[e[0]], b = P[e[1]]; return `<line x1="${a.x.toFixed(0)}" y1="${a.y.toFixed(0)}" x2="${b.x.toFixed(0)}" y2="${b.y.toFixed(0)}" stroke="#d8c8a8" stroke-width="${(0.4+2.4*e[2]/emax).toFixed(1)}" opacity="0.45"/>`; }).join('')}
      ${P.map(p => { const r = 4+10*Math.sqrt(p.n[1]/maxc), col = p.n[2] || '#a8330d', href = p.n[3] || ('#/anu/concept/' + encodeURIComponent(p.n[0]));
        return `<a href="${href}"><circle cx="${p.x.toFixed(0)}" cy="${p.y.toFixed(0)}" r="${r.toFixed(1)}" fill="${col}" opacity="0.88"><title>${esc(disp(p.n[0]))} · ${p.n[1]}</title></circle>
          <text x="${(p.x+r+2).toFixed(0)}" y="${(p.y+4).toFixed(0)}" font-size="${(9+4*Math.sqrt(p.n[1]/maxc)).toFixed(0)}" fill="#4a3f33">${esc(disp(p.n[0]))}</text></a>`; }).join('')}
    </svg>`;
  }
  window._drawCiteNet = drawCiteNet;
})();
