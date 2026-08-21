/* Anukramaṇikā — the corpus index. Three ways in, all of them alphabetical or numeric
   rather than positional, which is what a printed edition's back matter gives you and the
   reader so far did not: search finds a string you already know, an index shows you what
   is there.

     प्रतीक   first lines of all 20,389 verses and 4,497 mūla passages
     विषयाः   the 1,482 topic headings, gathered across works
     सङ्ख्या  numbered references — sūtra, adhyāya, verse — browsed as a table

   Sorted by DEVANĀGARĪ codepoint, not by the romanised search key: the Unicode Devanāgarī
   block runs in varṇamālā order (अ आ इ … क ख ग …), so a plain codepoint sort is already the
   traditional order, whereas sorting the roman skeleton would interleave क and च under 'c'
   and put ऋ nowhere a paṇḍita would look.

   Reuses globals from app.js: q(), disp(), view(), status(), wname(), esc via local copy. */
(function () {
  const esc = s => (s || '').replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));

  // Devanāgarī letters that can open a word: independent vowels and consonants. A pratīka
  // is bucketed by its first such letter, so matras and the ornament that opens a line
  // (ॐ, daṇḍas, quote marks, verse numbers) never become a heading of their own.
  const OPENER = /[अ-औक-हक़-य़]/;
  const LEAD = /^[\sॐ।॥"“”'‘’()\[\]*०-९0-9.\-–—]+/;

  function pratika(t) {
    let s = (t || '').replace(LEAD, '');
    const cut = s.search(/[।॥]/);
    if (cut > 8) s = s.slice(0, cut);
    s = s.trim();
    return s.length > 66 ? s.slice(0, 66) + '…' : s;
  }

  const firstLetter = s => {
    for (const ch of s || '') if (OPENER.test(ch)) return ch;
    return '';
  };

  let CACHE = null;
  function build() {
    if (CACHE) return CACHE;
    status('building index…');
    const rows = q("SELECT work, seq, content_type, text_dev, verse, adhyaya FROM entries "
                 + "WHERE (is_padya=1 OR content_type='Mula') AND text_dev IS NOT NULL");
    const items = [];
    for (const r of rows) {
      const p = pratika(r.text_dev);
      if (p.length < 4) continue;
      const L = firstLetter(p);
      if (!L) continue;
      items.push({p, L, w: r.work, s: r.seq, v: r.verse, a: r.adhyaya, m: r.content_type === 'Mula'});
    }
    items.sort((x, y) => x.p.localeCompare(y.p, 'sa'));
    const letters = {};
    for (const it of items) (letters[it.L] = letters[it.L] || []).push(it);

    const topics = q("SELECT work, seq, content_type, text_dev FROM entries "
                   + "WHERE content_type LIKE 'Heading%' AND text_dev IS NOT NULL")
      .map(r => ({t: r.text_dev.trim(), w: r.work, s: r.seq, lv: +(r.content_type.slice(-1)) || 0}))
      .filter(r => r.t.length > 1)
      .sort((a, b) => a.t.localeCompare(b.t, 'sa'));

    CACHE = {items, letters, topics};
    status('');
    return CACHE;
  }

  const link = (w, s, label, cls) =>
    `<a class="${cls || 'ixl'}" href="#/b/${w}/${s}">${label}</a>`;

  function head(sub) {
    const tab = (k, dev, en) =>
      `<a class="atab${sub === k ? ' on' : ''}" href="#/idx/${k}">${disp(dev)} <span class="ixen">${en}</span></a>`;
    return `<div class="anav">${tab('pratika', 'प्रतीकाः', 'First lines')}`
         + `${tab('topic', 'विषयाः', 'Topics')}${tab('ref', 'सङ्ख्याः', 'References')}</div>`;
  }

  function pratikaView(letter) {
    const {letters} = build();
    const keys = Object.keys(letters).sort((a, b) => a.localeCompare(b, 'sa'));
    if (!letter || !letters[letter]) letter = keys[0];
    const bar = keys.map(k =>
      `<a class="ixk${k === letter ? ' on' : ''}" href="#/idx/pratika/${encodeURIComponent(k)}">${disp(k)}`
      + `<em>${letters[k].length}</em></a>`).join('');
    const rows = letters[letter].map(it => {
      const ref = it.v != null ? `${it.a != null ? disp(String(it.a)) + '.' : ''}${disp(String(it.v))}` : '';
      return `<div class="ixrow">${link(it.w, it.s, esc(disp(it.p)), 'ixp')}`
           + `<span class="ixw">${wname(it.w)}${ref ? ' · ' + ref : ''}</span></div>`;
    }).join('');
    return head('pratika')
      + `<div class="ixkeys">${bar}</div>`
      + `<div class="ixcount">${letters[letter].length.toLocaleString()} under ${disp(letter)}</div>`
      + `<div class="ixlist">${rows}</div>`;
  }

  function topicView() {
    const {topics} = build();
    const rows = topics.map(t =>
      `<div class="ixrow">${link(t.w, t.s, esc(disp(t.t)), 'ixp')}`
      + `<span class="ixw">${wname(t.w)}</span></div>`).join('');
    return head('topic') + `<div class="ixcount">${topics.length.toLocaleString()} topics</div>`
         + `<div class="ixlist">${rows}</div>`;
  }

  function refView(slug) {
    const works = q("SELECT slug,title FROM works ORDER BY ord");
    const withRefs = q("SELECT work, COUNT(*) c FROM entries WHERE verse IS NOT NULL GROUP BY work");
    const has = Object.fromEntries(withRefs.map(r => [r.work, r.c]));
    const list = works.filter(w => has[w.slug]);
    if (!slug || !has[slug]) slug = list.length ? list[0].slug : '';
    const picks = list.map(w =>
      `<a class="ixk${w.slug === slug ? ' on' : ''}" href="#/idx/ref/${w.slug}">${wname(w.slug, w.title)}`
      + `<em>${has[w.slug]}</em></a>`).join('');
    const rows = slug ? q("SELECT seq, adhyaya, verse, text_dev FROM entries WHERE work=? "
                        + "AND verse IS NOT NULL ORDER BY seq", [slug]).map(r =>
      `<div class="ixrow"><span class="ixn">${r.adhyaya != null ? disp(String(r.adhyaya)) + '.' : ''}`
      + `${disp(String(r.verse))}</span>${link(slug, r.seq, esc(disp(pratika(r.text_dev))), 'ixp')}</div>`).join('') : '';
    return head('ref') + `<div class="ixkeys">${picks}</div><div class="ixlist">${rows}</div>`;
  }

  window.renderIndex = function (sub, arg) {
    try {
      const html = sub === 'topic' ? topicView()
                 : sub === 'ref' ? refView(arg)
                 : pratikaView(arg);
      view().innerHTML = `<h2 class="wtitle">${disp('अनुक्रमणिका')}</h2>` + html;
      window.scrollTo(0, 0);
    } catch (e) {
      status('index error: ' + e.message);
    }
  };
})();
