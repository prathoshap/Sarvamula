/* Sarvamūla reader — metadata-rich. Topics (Heading0–4), mūla/commentary, pramāṇa citations (kutra),
   variant readings, 10-script display via BhagDisplay. */
let DB=null, script=localStorage.getItem('sv_script')||'deva';
// No stored script means this reader has never been here: show the opening page rather than
// dropping them straight into the library.
let _welcome=!localStorage.getItem('sv_script');
const view=()=>document.getElementById('view'), status=t=>{document.getElementById('status').textContent=t||'';};
const disp=dev=>window.BhagDisplay?BhagDisplay(dev||'',script):(dev||'');
window.disp=disp;   // anusandhana.js renders pramāṇa names in the chosen script
// search normalization (norm) — VOWEL-PRESERVING. MUST stay byte-identical to
// norm() in build_db.py (which builds text_skel). Keeps vowels (long→short), folds
// aspirates/retroflex/sibilants, drops anusvāra/visarga, vocalic-ṛ → "ri".
const _CONS={'क':'k','ख':'k','ग':'g','घ':'g','ङ':'n','च':'c','छ':'c','ज':'j','झ':'j','ञ':'n','ट':'t','ठ':'t','ड':'d','ढ':'d','ण':'n','त':'t','थ':'t','द':'d','ध':'d','न':'n','प':'p','फ':'p','ब':'b','भ':'b','म':'m','य':'y','र':'r','ल':'l','व':'v','श':'s','ष':'s','स':'s','ह':'h','ळ':'l'};
const _MATRA={'ा':'a','ि':'i','ी':'i','ु':'u','ू':'u','ृ':'ri','ॄ':'ri','ॢ':'li','ॣ':'li','े':'e','ै':'e','ो':'o','ौ':'o'};
const _IND={'अ':'a','आ':'a','इ':'i','ई':'i','उ':'u','ऊ':'u','ऋ':'ri','ॠ':'ri','ऌ':'li','ॡ':'li','ए':'e','ऐ':'e','ओ':'o','औ':'o'};
function norm(s){s=s||'';
  if(/[ऀ-ॿ]/.test(s)){
    let o='',i=0;const n=s.length;
    while(i<n){const ch=s[i];
      if(ch in _CONS){o+=_CONS[ch];const nx=i+1<n?s[i+1]:'';
        if(nx==='्'){i+=2;continue;}
        if(nx in _MATRA){o+=_MATRA[nx];i+=2;continue;}
        o+='a';i+=1;continue;}
      if(ch in _IND){o+=_IND[ch];i+=1;continue;}
      if(ch in _MATRA){o+=_MATRA[ch];i+=1;continue;}
      if(ch==='ॐ'){o+='om';i+=1;continue;}
      if(/[\s।॥]/.test(ch)){o+=' ';i+=1;continue;}
      i+=1;}                                       // drop anusvāra/visarga/avagraha/digits/ZWJ
    return o.replace(/\s+/g,' ').trim();}
  return s.toLowerCase().replace(/[ṃṁḥ]/g,'').replace(/ṭ/g,'t').replace(/ḍ/g,'d')
    .replace(/[ṇṅñ]/g,'n').replace(/[ḷḻ]/g,'l').replace(/ś|ṣ|sh/g,'s').replace(/ch/g,'c')
    .replace(/([kgtdpbjc])h/g,'$1')
    .replace(/[āâ]/g,'a').replace(/[īî]/g,'i').replace(/[ūû]/g,'u').replace(/[ēê]/g,'e').replace(/[ōô]/g,'o')
    .replace(/[ṛṝ]/g,'ri')
    // The DIPHTHONGS must fold the same way the Devanāgarī branch folds them, or roman input
    // can never match the skeletons: ै and ौ collapse to 'e' and 'o' above (_MATRA/_IND), so
    // द्वैत becomes "dveta" while a typed "dvaita" stayed "dvaita" — no match for dvaita or
    // advaita anywhere in 37 works, though the Devanāgarī spelling found them. Roman 'ai'/'au'
    // therefore fold too, which also makes jaimini/kaustubha agree with जैमिनि/कौस्तुभ.
    .replace(/ai/g,'e').replace(/au/g,'o')
    .replace(/[^a-z ]/g,'').replace(/\s+/g,' ').trim();}
const fold=norm;   // legacy alias
function q(sql,args){const st=DB.prepare(sql);st.bind(args||[]);const o=[];while(st.step())o.push(st.getAsObject());st.free();return o;}
// inline markup on transliterated text: quoted pramāṇa ‘…’ + parenthetical refs
function mk(s){return s.replace(/‘([^‘’]{2,})’/g,'<span class="quote">‘$1’</span>').replace(/\(([^()]{1,28})\)/g,'<span class="cite">($1)</span>');}
// highlight matched words in a search hit (script-agnostic), snippet long blocks around the match
function hl(dev,toks){
  const words=(dev||'').split(/\s+/).filter(Boolean); let first=-1;
  const m=words.map((w,i)=>{const sk=fold(w);const hit=toks.some(t=>t&&sk.includes(t));if(hit&&first<0)first=i;return{d:disp(w),hit};});
  let lo=0,hi=m.length;
  if(m.length>46&&first>=0){lo=Math.max(0,first-20);hi=Math.min(m.length,first+26);}
  const seg=m.slice(lo,hi).map(x=>x.hit?`<mark>${x.d}</mark>`:x.d).join(' ');
  return (lo>0?'… ':'')+seg+(hi<m.length?' …':'');
}

// Verse layout: split a Devanāgarī verse on its daṇḍa runs so each pāda sits on
// its own line; a line ending in ॥ closes a śloka and gets a little breathing room.
// (Handles ॥ १ ॥, ॥ *॥, ॥ १/१/१॥ and lone unnumbered ॥.) Operates on Devanāgarī
// BEFORE disp() so the split is script-independent; disp/mk applied per line.
function verseLines(dev){
  var SEP='\u0001';
  return (dev||'')
    .replace(/[\u0964\u0965][ \d\u0966-\u096f*/\u0964\u0965]*[\u201d\u2019]?/g, function(m){ return m+SEP; })
    .split(SEP).map(function(s){ return s.trim(); }).filter(Boolean)
    .map(function(t){ return {t:t, end:/\u0965[\u201d\u2019]?\s*$/.test(t)}; });   // ends in ॥ -> śloka boundary
}
function verseHTML(dev){
  const ls = verseLines(dev);
  if(ls.length < 2) return mk(disp(dev));                // nothing to split
  return `<div class="verse">`+ls.map(l =>
    `<span class="pada${l.end?' pe':''}">${mk(disp(l.t))}</span>`).join('')+`</div>`;
}
// ── Audio + karaoke ────────────────────────────────────────────────────────
// Emulates the Bhāgavata-VāNi player: display lines are baked at BUILD time (audio.lines,
// "\n"-joined) and timings reference those line indices ([{s,e,ln:[i]}]), so karaoke is
// just a class toggle on <span class="ln" data-i>. No character-offset mapping anywhere.
// AUDIO_BASE: the sarvamula R2 bucket. `sv_audio` in localStorage still overrides it — set it
// to 'audio' to read the local web/audio tree instead, which is how a freshly cut work is
// checked by ear before it is uploaded.
const AUDIO_BASE=(localStorage.getItem('sv_audio')||'https://pub-f4f244dc7f1b4ad2ad5c4116104064ed.r2.dev').replace(/\/+$/,'');
// bump to invalidate cached audio. The m4a carry Cache-Control: immutable, max-age=1y, so a
// file REPLACED at the same path is otherwise pinned in a listener's browser for a year —
// which is exactly what happened on 2026-08-17, when 231 re-assembled blocks were uploaded
// over their old paths and the corrected audio could not reach anyone who had already played it.
// Any re-bake that keeps a path MUST bump this, not just DB_REV.
const AUDIO_REV='8';
// A row may stream from a DIFFERENT bucket: Bhāgavata Tātparya's 16,017 mūla verses were
// already rendered for Bhāgavata-VāNi, so one work reads from two buckets. The column holds a
// short TOKEN rather than the URL — stored in full it was the same 64 characters on every one
// of those rows, 1 MB of the database saying the same thing.
const BASES={ bhv:'https://pub-303f7559721c4b40bf6712eb557e350c.r2.dev/Bhagavata_Audio' };
const abase=b=>(b?(BASES[b]||b):AUDIO_BASE);
let _audioFor=null;              // {seq: [rows]} for the open chapter
function audioRows(seq){
  // `base` overrides AUDIO_BASE per row. Bhāgavata Tātparya streams its 16,017 mūla verses
  // from the Bhāgavata-VāNi bucket (already rendered there, with timings) while its own
  // commentary comes from ours — one work, two buckets.
  try{ return q("SELECT block,part,path,dur,kind,lines,base FROM audio WHERE work=? AND seq=? ORDER BY kind='mula' DESC, part",[_cache.slug,seq]); }
  catch(e){ return []; }         // table absent until audio is built
}
// Every entry recited by SOME audio part. The part bakes that text into its own display
// lines, so the entry must not also print its raw body — that was the same text twice,
// once under the player and once as the plain row.
let _covSlug=null,_cov=null;
function audioCovered(){
  if(_covSlug===_cache.slug) return _cov;
  _covSlug=_cache.slug; _cov=new Set();
  try{ for(const r of q("SELECT covers FROM audio WHERE work=?",[_cache.slug]))
         for(const s of JSON.parse(r.covers||'[]')) _cov.add(s); }
  catch(e){}
  return _cov;
}
function audioSegs(block,part){
  try{ const r=q("SELECT segs FROM audio_timings WHERE block=? AND part=?",[block,part]);
       return r.length?JSON.parse(r[0].segs):null; }catch(e){ return null; }
}
// One <span class="ln"> per PADA — Bhāgavatam's shape, at pāda granularity. Verse and
// prose are marked so they can be set differently: a śloka wants its pādas on their own
// centred lines, prose wants clauses flowing. Lines are stored as JSON [{t,k}] rather
// than "\n"-joined text precisely so the kind travels with each line.
// Mark the searched word inside a baked display line. Word-level and fold()-based — the same
// test the search itself ran — so an avagraha, a svara mark or a script change cannot break a
// match that the search already found. A plain indexOf would: `sोऽध्वनः` loses its avagraha on
// the way into the URL and would then match nothing.
function lineHTML(t,term){
  const f=term?fold(term):''; if(!f) return disp(t);
  return (t||'').split(/(\s+)/).map(w=>
    w.trim()&&fold(w).includes(f) ? `<mark class="cithit">${disp(w)}</mark>` : disp(w)).join('');
}
function audioLines(raw,pid,term){
  let L; try{ L=JSON.parse(raw||'[]'); }catch(e){ L=(raw||'').split('\n').map(t=>({t,k:'gadya'})); }
  let out='',prev=null;
  L.forEach((l,i)=>{
    if(prev&&prev!==l.k) out+=`</div><div class="alines ${l.k}">`;
    // a gap line has no seg — render it inert rather than wiring a seek that cannot fire
    out+= l.k==='gap'
      ? `<span class="ln" data-i="${i}">${l.t}</span>`
      : `<span class="ln" data-i="${i}" onclick="svSeek('${pid}',${i})">${lineHTML(l.t,term)}</span>`;
    prev=l.k;
  });
  return `<div class="alines ${L.length?L[0].k:'gadya'}">${out}</div>`;
}
// Which entry's tile PRINTS a given entry's text. An entry recited by another part prints
// nothing of its own (see audioCovered), so a deep link to it has no #b<seq> to scroll to and
// no place to put the highlight — both belong on the covering tile.
let _anchSlug=null,_anch=null;
function audioAnchor(seq){
  if(seq==null) return null;
  if(_anchSlug!==_cache.slug){
    _anchSlug=_cache.slug; _anch=new Map();
    try{ for(const r of q("SELECT seq,covers FROM audio WHERE work=?",[_cache.slug]))
           for(const s of JSON.parse(r.covers||'[]')) _anch.set(s,r.seq); }catch(e){}
  }
  return _anch.has(seq)?_anch.get(seq):seq;
}

function audioHTML(seq,term){
  const rows=audioRows(seq); if(!rows.length) return '';
  return `<div class="audio">`+rows.map(a=>{
    const pid=a.block+'_'+a.part;
    return `<div class="apart${a.kind==='mula'?' mula':''}" id="ap_${pid}">
      <button class="aplay" onclick="svPlay('${pid}')">▶</button>
      <span class="alab">${({sutra:'सूत्र',upanishad:'उपनिषत्',mula:'मूल',recited:'पाठः',bhashya:'भाष्य '+a.part,tatparya:'तात्पर्य '+a.part,vyakhyana:'अनुव्याख्यान '+a.part,nirnaya:'निर्णय '+a.part,bhaga:'भाग '+a.part})[a.kind]||a.part} · ${a.dur.toFixed(0)}s</span>
      ${audioLines(a.lines,pid,term)}</div>`;
  }).join('')+`</div>`;
}

// Open-work cache: {slug, chaps, title}. Declared here with the other module state rather
// than beside renderWork — it lived between sideTopics and renderWork and was lost when that
// region was rewritten, which threw "ReferenceError: _cache is not defined" at load because
// `let` bindings are not hoisted into a usable state.
let _cache={};
// ── pārāyaṇa player ──────────────────────────────────────────────────────────
// Continuous recitation. The queue is every tile of the open work in reading order — the
// audio rows are already ordered by (seq, part) — so "next" needs no new data. When a track
// ends the next one starts, which is what makes a whole pāda, adhyāya or grantha playable
// without touching anything. Speed is applied on every play() because some browsers reset
// playbackRate when the source changes.
const ico=n=>`<svg aria-hidden="true"><use href="#i-${n}"/></svg>`;
let _raf=0, _queue=[], _qwork=null, _rate=parseFloat(localStorage.getItem('sv_rate')||'1'), _loop=false, _tick=0;

function svQueue(){
  if(_qwork===_cache.slug) return _queue;
  _qwork=_cache.slug;
  try{ _queue=q("SELECT block,part FROM audio WHERE work=? ORDER BY seq, part",[_cache.slug])
                 .map(r=>r.block+'_'+r.part); }catch(e){ _queue=[]; }
  return _queue;
}
function svStep(d){ const Q=svQueue(), i=Q.indexOf(_pid); return i<0?null:(Q[i+d]||null); }

function svGo(pid,fromStart){
  if(!pid||!svLoad(pid)) return;
  const start=()=>{
    if(fromStart){ try{ _au.currentTime=0; }catch(e){} }
    _au.playbackRate=_rate;
    const p=_au.play(); if(p&&p.catch) p.catch(()=>{});
  };
  if(_au.readyState>=1) start(); else _au.addEventListener('loadedmetadata',start,{once:true});
  svFocus(pid);
  svBar();
}

// Bring the recited text on screen. The reader renders ONE chapter, but a queue runs through
// the whole work — so the next track is usually in a chapter that is not in the DOM at all,
// and scrolling to it silently did nothing (the page sat on the first chapter for the entire
// recitation). If the tile is absent, navigate to the chapter that holds it first; playback
// is unaffected because the audio element is independent of the DOM.
function svFocus(pid){
  const here=document.getElementById('ap_'+pid);
  if(here){ here.scrollIntoView({behavior:'smooth',block:'center'}); return; }
  const i=pid.lastIndexOf('_'), block=pid.slice(0,i), part=+pid.slice(i+1);
  let seq=null;
  try{ seq=q("SELECT seq FROM audio WHERE block=? AND part=?",[block,part])[0].seq; }catch(e){ return; }
  const chaps=_cache.chaps||[];
  const ci=chaps.findIndex(c=>c.rows.some(r=>r.seq===seq));
  if(ci<0 || ci===_cache.chIdx) return;
  location.hash=`#/w/${_cache.slug}/${ci}`;      // re-renders; the audio keeps playing
  setTimeout(()=>{
    const el=document.getElementById('ap_'+pid);
    if(el) el.scrollIntoView({behavior:'smooth',block:'center'});
    svLight(null);
  }, 80);
}
function svAdvance(){
  svLight(null);
  if(_loop){ svGo(_pid,true); return; }          // repeat this pāda / adhyāya
  const n=svStep(1);
  if(n) svGo(n,true); else svBar();
}

const mmss=t=>isFinite(t)?`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`:'0:00';

function svBar(){
  let bar=document.getElementById('nowbar');
  if(!bar){
    bar=document.createElement('div'); bar.id='nowbar';
    bar.innerHTML=`<button id="nbPrev" title="previous">${ico('prev')}</button>
      <button id="nbPlay" title="play / pause">${ico('play')}</button>
      <button id="nbNext" title="next">${ico('next')}</button>
      <span class="nblab" id="nbLab"></span>
      <input type="range" id="nbSeek" min="0" max="1000" value="0" title="seek">
      <span class="nbt" id="nbT">0:00</span>
      <select id="nbRate" title="recitation speed">
        <option value="0.7">0.7×</option><option value="0.8">0.8×</option>
        <option value="0.9">0.9×</option><option value="1">1×</option>
        <option value="1.1">1.1×</option><option value="1.25">1.25×</option>
        <option value="1.5">1.5×</option></select>
      <button class="nbloop" id="nbLoop" title="repeat this track">āvṛtti</button>
      <button id="nbClose" title="stop">${ico('close')}</button>`;
    document.body.appendChild(bar);
    document.getElementById('nbPlay').onclick=()=>{
      if(_au.paused){ _au.playbackRate=_rate; _au.play(); } else _au.pause(); svBar(); };
    document.getElementById('nbPrev').onclick=()=>{ const p=svStep(-1); if(p) svGo(p,true); };
    document.getElementById('nbNext').onclick=()=>{ const n=svStep(1); if(n) svGo(n,true); };
    document.getElementById('nbClose').onclick=()=>{
      _au.pause(); bar.classList.remove('on'); document.body.classList.remove('playing'); };
    const rs=document.getElementById('nbRate');
    rs.value=String(_rate);
    rs.onchange=e=>{ _rate=+e.target.value; localStorage.setItem('sv_rate',_rate);
                     if(_au) _au.playbackRate=_rate; };
    document.getElementById('nbLoop').onclick=e=>{ _loop=!_loop;
      e.target.classList.toggle('on',_loop); };
    document.getElementById('nbSeek').oninput=e=>{
      if(_au&&isFinite(_au.duration)) _au.currentTime=_au.duration*e.target.value/1000; };
  }
  if(!_au||!_pid) return;
  bar.classList.add('on'); document.body.classList.add('playing');
  const i=_pid.lastIndexOf('_'), block=_pid.slice(0,i), part=+_pid.slice(i+1);
  let lab=_cache.title||_cache.slug||'';
  try{
    const r=q("SELECT kind,ref FROM audio WHERE block=? AND part=?",[block,part])[0];
    const K={sutra:'सूत्र',upanishad:'उपनिषत्',mula:'मूल',recited:'पाठः',bhashya:'भाष्य',tatparya:'तात्पर्य',
             vyakhyana:'अनुव्याख्यान',nirnaya:'निर्णय'};
    lab += ' · ' + ((K[r.kind]||'') + (r.ref?' '+r.ref:''));
  }catch(e){}
  document.getElementById('nbLab').textContent=lab;
  document.getElementById('nbPlay').innerHTML=ico(_au.paused?'play':'pause');
  const Q=svQueue(), at=Q.indexOf(_pid);
  document.getElementById('nbT').textContent =
    mmss(_au.currentTime)+' / '+mmss(_au.duration)+(at>=0?`  ${at+1}/${Q.length}`:'');
  const sk=document.getElementById('nbSeek');
  if(isFinite(_au.duration)&&_au.duration>0) sk.value=Math.round(1000*_au.currentTime/_au.duration);
}

// play a work from its first track — the pārāyaṇa entry point
function svStartWork(){ const Q=svQueue(); if(Q.length) svGo(Q[0],true); }
window.svStartWork=svStartWork;

let _au=null,_segs=null,_pid=null;
// Load (but do not start) a part. Setting .src is ASYNCHRONOUS: assigning currentTime
// before the media is ready is silently discarded and playback begins at 0 — which is
// why clicking a pāda used to jump to the top of the block. svAt() waits for metadata.
function svLoad(pid){
  const i=pid.lastIndexOf('_'), block=pid.slice(0,i), part=+pid.slice(i+1);
  const row=q("SELECT path,base FROM audio WHERE block=? AND part=?",[block,part])[0]; if(!row)return false;
  if(!_au){
    _au=new Audio(); _au.preload='metadata';
    // Karaoke runs on requestAnimationFrame, NOT on timeupdate. timeupdate fires roughly
    // four times a second, so the highlight trailed the voice by up to ~250 ms — audible as
    // the sound running ahead of the text, and worst on long recited blocks. rAF gives one
    // frame (~16 ms). timeupdate still drives the progress bar, where 250 ms does not show.
    const frame=()=>{ if(_au && !_au.paused && !_au.ended){ svKaraoke(); _raf=requestAnimationFrame(frame); }
                      else _raf=0; };
    _au.onplay=()=>{ svBar(); if(!_raf) _raf=requestAnimationFrame(frame); };
    _au.ontimeupdate=()=>{ if(!_raf) svKaraoke(); if(++_tick%4===0) svBar(); };
    _au.onended=()=>{ if(_raf){cancelAnimationFrame(_raf); _raf=0;} svAdvance(); };
    _au.onpause=()=>{ if(_raf){cancelAnimationFrame(_raf); _raf=0;} svBar(); };
    _au.onseeked=svKaraoke;
  }
  if(_pid!==pid){
    _pid=pid; _segs=audioSegs(block,part);
    // AUDIO_REV busts any copy cached before the files were re-muxed with +faststart —
    // without the moov atom up front the browser cannot seek and silently plays from 0.
    _au.src=abase(row.base)+'/'+row.path+'?r='+AUDIO_REV_LIVE; _au.load();
  }
  document.querySelectorAll('.apart').forEach(e=>e.classList.toggle('on',e.id==='ap_'+pid));
  return true;
}
function svAt(ln){
  const seg=(_segs||[]).find(s=>(s.ln||[]).includes(ln));
  if(!seg){ console.warn('[audio] no seg for line',ln); return; }
  // Land a little EARLY. An AAC frame is 1024 samples (~23 ms), and a seek resolves to a
  // frame boundary — which can fall after the requested time, swallowing the first syllable
  // of the pāda you clicked. Continuous playback never seeks, which is why it sounded fine.
  // 40 ms costs at most the tail of the previous pāda and guarantees the attack survives.
  // Seek to `q` — the pause BEFORE the pāda, measured in the built file and stored with the
  // seg. Our recited segs abut (block N ends exactly where N+1 begins, because that is what
  // the taps define), so aiming at seg.s puts a frame-quantised seek inside the first
  // syllable. TTS pādas sit behind 0.25 s of assembled silence, which absorbs the same
  // imprecision invisibly — the reason this only ever showed up on recordings. A measured
  // point beats a guessed lead: where no pause exists, fall back to a fixed one.
  const SEEK_LEAD=0.150;
  const target=(seg.q!=null&&seg.q<=seg.s) ? seg.q
             : Math.max(0, seg.s - (seg.s>SEEK_LEAD ? SEEK_LEAD : 0));
  const settle=()=>{                       // some browsers reset currentTime as playback
    if(Math.abs(_au.currentTime-target)>1.0) _au.currentTime=target;   // starts — re-assert
  };
  const go=()=>{
    // NEVER fastSeek. It is explicitly allowed to land on a nearby frame rather than the
    // time asked for, and it lands late as often as early — which ate the first syllable of
    // whichever pāda was clicked. currentTime is the accurate seek.
    //
    // And WAIT for the seek to land before playing. Calling play() straight after assigning
    // currentTime starts playback while the seek is still resolving, so the browser begins
    // wherever it happens to be — a little past the mark — and the opening syllable is gone.
    // Continuous playback never seeks, which is why only clicked pādas lost their attack.
    const start=()=>{
      // Report where the browser ACTUALLY landed. If an attack is still being lost, this
      // number says by how much, instead of leaving it to be guessed at.
      const miss=_au.currentTime-target;
      if(Math.abs(miss)>0.02) console.log(`[audio] seek asked ${target.toFixed(3)}s, landed `
        +`${_au.currentTime.toFixed(3)}s (${miss>0?'+':''}${(miss*1000).toFixed(0)} ms)`);
      svLight(seg.ln);
      const p=_au.play();
      if(p&&p.catch) p.catch(err=>console.warn('[audio] play blocked',err));
      setTimeout(settle,80); setTimeout(settle,300);
    };
    if(Math.abs(_au.currentTime-target)<0.005){ start(); return; }
    _au.addEventListener('seeked',start,{once:true});
    try{ _au.currentTime=target; }catch(e){ setTimeout(start,60); }
  };
  if(_au.readyState>=1) go();                                  // HAVE_METADATA: safe to seek
  else _au.addEventListener('loadedmetadata',go,{once:true});
}
function svPlay(pid){
  if(!svLoad(pid))return;
  if(_au.paused){ _au.playbackRate=_rate; _au.play(); } else _au.pause();
  svBar();
}
// clicking a line SEEKS — never a play/pause toggle, or clicking mid-playback would pause
function svSeek(pid,ln){ if(!svLoad(pid))return; svAt(ln); }
function svKaraoke(){
  if(!_segs||!_pid)return;
  const t=_au.currentTime; let seg=null;
  for(const s of _segs){ if(t>=s.s) seg=s; else break; }   // last line started ≤ t stays lit through the gap
  svLight(seg?(seg.ln||[]):null);
}
function svLight(lit){
  const el=document.getElementById('ap_'+_pid); if(!el)return;
  el.querySelectorAll('.ln').forEach(l=>l.classList.toggle('now',!!lit&&lit.includes(+l.dataset.i)));
}
window.svPlay=svPlay; window.svSeek=svSeek;

function block(r){
  const ct=r.content_type||'';
  if(ct.startsWith('Heading')){const lv=r.heading_level||0;return `<div class="topic lv${lv}" id="b${r.seq}">${disp(r.text_dev)}</div>`;}
  if(ct==='Skandha_Heading'||ct==='Title'||ct==='Heading1')return `<div class="topic lv1" id="b${r.seq}">${disp(r.text_dev)}</div>`;
  if(ct==='Adhyaya_Heading'||ct==='Subheading')return `<div class="topic lv2" id="b${r.seq}">${disp(r.text_dev)}</div>`;
  if(ct==='Subject')return `<div class="topic lv3" id="b${r.seq}">${disp(r.text_dev)}</div>`;
  if(/Colophon/.test(ct))return `<div class="colo" id="b${r.seq}">${disp(r.text_dev)}</div>`;
  const isMula=(ct==='Mula'||ct==='Bhagavatam'), isT=(ct==='Tatparya'), isP=r.pramana;
  const cls=isT?'tat':(isMula?'mula':(isP?'pram':''));
  const ref=[r.skandha,r.adhyaya,r.verse].filter(x=>x!=null).join('.');
  const lbl=isT?('tātparya '+ref).trim():(isMula?('mūla '+ref).trim():(isP?'pramāṇa':ref));
  let src='';
  if(r.kutra){try{const k=[...new Set(JSON.parse(r.kutra))];src=`<div class="src">— ${k.map(x=>disp(x)).join(' · ')}</div>`;}catch(e){}}  // de-duped source list
  const refHtml=lbl?`<div class="ref">${lbl}</div>`:'';
  const tgt = r.seq===_hlSeq;
  const bodyHTML = (tgt && _hlTerm && r.is_padya) ? termBody(r.text_dev, _hlTerm)   // verse locus: still highlight the word
                 : r.is_padya ? verseHTML(r.text_dev)
                 : proseBody(r.text_dev, tgt?_hlQuote:'', tgt?_hlTerm:'');
  // Audio hangs off whichever entry the build anchored the part to — the Mula row for a
  // sūtra, the Sarvamula row for its bhāṣya, the first entry of the adhikaraṇa in
  // Anuvyākhyāna (which has no Mula at all). Where a part is anchored its display lines
  // REPLACE the raw body: same text, split per pāda, and clickable. An entry that some
  // other part recites prints nothing of its own — its text already appears there.
  // the tile that prints the target entry's text carries the highlight, even when the target
  // is a different (covered) entry whose own row prints nothing
  const au=audioHTML(r.seq, (_hlTerm && audioAnchor(_hlSeq)===r.seq) ? _hlTerm : '');
  if(au) return `<div class="v ${cls}" id="b${r.seq}">${refHtml}${au}${src}</div>`;
  if(audioCovered().has(r.seq)) return '';
  return `<div class="v ${cls}" id="b${r.seq}">${refHtml}<div class="body">${bodyHTML}</div>${src}</div>`;
}
// Prose/commentary block: Madhva's prose flows; each quoted pramāṇa “…” goes on its own
// coloured line (de-cluttered). If hlQuote is set (citation deep-link), highlight that span.
let _hlSeq=null, _hlQuote='', _hlTerm='';
function proseBody(dev, hlQuote, hlTerm){
  const rx=/[“‘][^”’]{2,}?[”’]/g, pre=(hlQuote||'').slice(0,22);
  // disp a Devanāgarī segment; if hlTerm is set, wrap its occurrences in a highlight
  const emit=(seg,isQ)=> (hlTerm && seg.indexOf(hlTerm)>=0)
      ? seg.split(hlTerm).map(p=>isQ?disp(p):mk(disp(p))).join(`<mark class="cithit">${disp(hlTerm)}</mark>`)
      : (isQ?disp(seg):mk(disp(seg)));
  let out='', last=0, m;
  while(m=rx.exec(dev)){
    if(m.index>last) out += emit(dev.slice(last,m.index),false);
    const hit = pre && m[0].slice(1).startsWith(pre);
    // keep the closing ” with its preceding daṇḍa (॥ is a line-break opportunity → would dangle)
    const qt = m[0].replace(/([।॥])\s*([”’])/g, '$1\u2060$2');
    out += `<span class="pram-q${hit?' cithit':''}">${emit(qt,true)}</span>`;
    last = m.index + m[0].length;
  }
  out += emit(dev.slice(last),false);
  return out;
}
// highlight a concept word inside a verse-locus block (flat render, word marked)
function termBody(dev, term){
  if(!term || dev.indexOf(term)<0) return verseHTML(dev);
  return dev.split(term).map(p=>mk(disp(p))).join(`<mark class="cithit">${disp(term)}</mark>`);
}
const CHAP_ORDER=['Skandha_Heading','Heading0','Heading1','Adhyaya_Heading','Title','Heading2','Subheading','Subject'];
// A colophon shortened to its closing phrase, for use as a chapter label.
// The marker is usually a word of its own (…प्रथमः पादः, …न्यासपद्धतिः समाप्ता), which the
// old pattern could not match because it demanded a character BEFORE the marker inside the
// same token. Everything therefore fell through to slice(-24), which cuts by code unit and
// so severed akṣaras — "ृता न्यासपद्धतिः समाप्ता", "रथमाध्यायस्य प्रथमः पादः". Both the match
// and the fallback now work in WHOLE WORDS, so a grapheme can never be split.
// A colophon of the shape "… <NAME> नाम <ordinal>ऽध्यायः" NAMES its chapter, and the name is
// what belongs in a chapter list — "सर्वशास्त्रार्थनिर्णयः", not "प्रथमोऽध्यायः". MBTN has no
// heading rows at all, so its 34 chapters were titled from the tail of each colophon and came
// out inconsistent: some the bare ordinal, some "नाम …", depending on how nāma had sandhi'd.
//
// It sandhis three ways, and all three occur in MBTN:
//   free            …निरूपणं नाम सप्तमोऽध्यायः
//   fused left      …पाण्डवोत्पत्तिर्नाम द्वादशोऽध्यायः      (visarga -> र्)
//   fused right     …निरूपणं नामाष्टमोऽध्यायः               (nāma + aṣṭama -> nāmāṣṭama)
// and the work's own name can fuse onto the front of the chapter name by avagraha:
//   …तात्पर्यनिर्णयेऽरणीप्राप्तिः  ->  अरणीप्राप्तिः
// Two chapters (11, 14) are printed with no name at all; those keep their ordinal.
function adhyayaName(t){
  const c=(t||'').replace(/[॥\s]+$/,'').replace(/\s+/g,' ').trim();
  const m=c.match(/^(.*?)(\s+|र्)नाम[ाै]?\s*\S*ऽ?ध्यायः$/);
  // No name printed at all (chapters 11 and 14): keep the ordinal, and ONLY the ordinal —
  // shortColo's two-token grab was dragging the work's name in front of it.
  if(!m){ const o=c.match(/(?:^|\s)(\S*ऽध्यायः)$/); return o?o[1]:''; }
  let n=(m[1].trim().split(/\s+/).pop()||'');
  if(m[2]==='र्') n+='ः';                       // the visarga was eaten by the sandhi
  const av=n.lastIndexOf('ऽ');                  // work name fused on by avagraha
  if(av>0 && n[av-1]==='े') n='अ'+n.slice(av+1);
  return n.replace(/ो$/,'ः').replace(/ं$/,'म्');
}
// Devanāgarī ordinals, for the chapters the edition prints with no name and for the one whose
// colophon is truncated in the source.
const ORDINALS=['','प्रथमः','द्वितीयः','तृतीयः','चतुर्थः','पञ्चमः','षष्ठः','सप्तमः','अष्टमः','नवमः','दशमः',
  'एकादशः','द्वादशः','त्रयोदशः','चतुर्दशः','पञ्चदशः','षोडशः','सप्तदशः','अष्टादशः','एकोनविंशः','विंशः',
  'एकविंशः','द्वाविंशः','त्रयोविंशः','चतुर्विंशः','पञ्चविंशः','षड्विंशः','सप्तविंशः','अष्टाविंशः',
  'एकोनत्रिंशः','त्रिंशः','एकत्रिंशः','द्वात्रिंशः','त्रयस्त्रिंशः','चतुस्त्रिंशः'];
const ordAdhyaya=i=>(ORDINALS[i]?ORDINALS[i].replace(/ः$/,'ोऽध्यायः'):'अध्यायः '+i);
function shortColo(t){
  const named=adhyayaName(t); if(named) return named;
  t=t.replace(/॥/g,'').replace(/\s+/g,' ').trim();
  const m=t.match(/((?:\S+\s+){0,1}\S*(?:ऽ?ध्यायः|पादः|प्रश्नः|खण्डः|सर्गः|समाप्त\S*|सम्पूर्ण\S*))\s*$/);
  return m?m[1].trim():t.split(' ').slice(-3).join(' ');
}
function chapters(rows){
  let ctype=null;
  for(const h of CHAP_ORDER){ if(rows.filter(r=>(r.content_type||'')===h).length>=2){ctype=h;break;} }
  const chaps=[];
  if(ctype){
    let cur={title:'प्रस्तावना',rows:[]};
    for(const r of rows){
      if((r.content_type||'')===ctype){ if(cur.rows.length)chaps.push(cur); cur={title:r.text_dev,rows:[r]}; }
      else cur.rows.push(r);
    }
    if(cur.rows.length)chaps.push(cur);
    if(chaps.length>1&&chaps[0].rows.length<=1)chaps.shift();          // drop empty preamble
  } else if(rows.some(r=>/Colophon/.test(r.content_type||''))){
    let cur={title:'',rows:[]},i=1;
    for(const r of rows){ cur.rows.push(r);
      // A colophon with no akṣara in it — MBTN has one that is a bare "॥" — is a fragment of
      // the previous one, not a chapter of its own. Closing a chapter on it invented an empty
      // 29th adhyāya and pushed every later number out by one.
      if(/Colophon/.test(r.content_type||'') && /[अ-ह]/.test(r.text_dev||'')){
        let t=shortColo(r.text_dev)||'';
        // A truncated colophon leaves the boilerplate behind ("इति …विरचिते") with the name
        // lost in the source. Better the plain ordinal than a title that says nothing.
        if(!t || /विरचिते|इति\s/.test(t)) t=ordAdhyaya(i);
        cur.title=t; chaps.push(cur); i++; cur={title:'',rows:[]}; } }
    if(cur.rows.length){cur.title=cur.title||ordAdhyaya(i);chaps.push(cur);}
  } else chaps.push({title:'—',rows});
  return chaps;
}
// Every type CHAP_ORDER can split a work on must count as a heading here, because
// renderWork drops the chapter's first row only when this says so — and the chapter title is
// already printed above it. 'Title' and 'Skandha_Heading' were missing, so Nyāya Vivaraṇa,
// which splits on Title, showed each of its 215 sūtra headings twice: once as the chapter
// title and again as the opening row.
const isHeading=r=>{const c=r.content_type||'';return c.startsWith('Heading')||['Adhyaya_Heading','Subheading','Subject','Title','Skandha_Heading'].includes(c);};
const hlvl=r=>{const c=r.content_type||'';if(c.startsWith('Heading'))return r.heading_level||0;return {Adhyaya_Heading:1,Subheading:1,Subject:2}[c]??1;};
// topics of the active chapter, nested in the sidebar (skip the chapter's own defining heading)
function sideTopics(ch){
  const rows=ch.rows; let hs=rows.filter(isHeading);
  if(rows.length&&isHeading(rows[0]))hs=hs.filter(r=>r.seq!==rows[0].seq);   // drop the title-heading itself
  if(!hs.length)return '';
  const base=Math.min(...hs.map(hlvl));
  return `<div class="ctopics">`+hs.map(r=>`<a class="ct l${Math.min(hlvl(r)-base,3)}" onclick="document.getElementById('b${r.seq}').scrollIntoView({behavior:'smooth'});return false;">${disp(r.text_dev)}</a>`).join('')+`</div>`;
}

const WDEV={
  brahmasutra:'ब्रह्मसूत्राणि', bhagavadgita:'भगवद्गीता',
  aitareya_bhashya:'ऐतरेयभाष्यम्', anu_vyakhyana:'अनुव्याख्यानम्', atharvana_bhashya:'आथर्वणभाष्यम्',
  bhagavata_tatparya:'भागवततात्पर्यनिर्णयः', chandogya_bhashya:'छान्दोग्यभाष्यम्', dvadasha_stotra:'द्वादशस्तोत्रम्',
  // The two Gītā slugs hold each other's text: the content under `gita_bhashya` closes
  // "…गीतातात्पर्यनिर्णय उपोद्घातः समाप्तः" and opens "नारायणं नमस्कृत्य गीतातात्पर्यमुच्यते",
  // while `gita_tatparya` closes "…गीताभाष्य उपोद्घातः समाप्तः". The slugs are wired into
  // 1,300 R2 object paths, so the NAMES are corrected here rather than the directories moved.
  gita_bhashya:'गीतातात्पर्यम्', gita_tatparya:'गीताभाष्यम्', ishavasya_bhashya:'ईशावास्यभाष्यम्',
  jayanti_kalpa:'जयन्तीनिर्णयः', kanva_bhashya:'काण्वभाष्यम्', karma_nirnaya:'कर्मनिर्णयः',
  katha_lakshana:'कथालक्षणम्', kathaka_bhashya:'काठकभाष्यम्', krshna_amrta_maharnava:'कृष्णामृतमहार्णवः',
  manduka_bhashya:'माण्डूक्यभाष्यम्', mayavada_khandana:'मायावादखण्डनम्', mbtn:'महाभारततात्पर्यनिर्णयः',
  nyasa_paddhati:'न्यासपद्धतिः', nyaya_vivarana:'न्यायविवरणम्', parishishta:'परिशिष्टम्',
  pramana_lakshana:'प्रमाणलक्षणम्', prapancha_mithyatva_khandana:'मिथ्यात्वानुमानखण्डनम्', rg_bhashya:'ऋग्भाष्यम्',
  sadachara_smriti:'सदाचारस्मृतिः', sangraha_bhashya:'सङ्ग्रहभाष्यम्', shatprashna_bhashya:'षट्प्रश्नभाष्यम्',
  sutra_bhashya:'ब्रह्मसूत्रभाष्यम्', taittiriya_bhashya:'तैत्तिरीयभाष्यम्', talavakara_bhashya:'तलवकारभाष्यम्',
  tantrasara_sangraha:'तन्त्रसारसङ्ग्रहः', tatva_sankhyana:'तत्त्वसङ्ख्यानम्', tatva_viveka:'तत्त्वविवेकः',
  tatvodyota:'तत्त्वोद्योतः', upadhi_khandana:'उपाधिखण्डनम्', vishnu_tatva_nirnaya:'विष्णुतत्त्वनिर्णयः',
  yamaka_bharata:'यमकभारतम्', yati_pranava_kalpa:'यतिप्रणवकल्पः',
};

const GROUPS=[
  // the root texts themselves, ahead of the commentaries on them: someone who wants to read
  // or hear the Sūtras or the Gītā should not have to open a bhāṣya to find them
  ['मूलग्रन्थाः','Mūla Texts',['brahmasutra','bhagavadgita']],
  // Bhāṣya before Tātparya, as they are studied. The slugs read backwards because each holds
  // the other's text (see WDEV) — `gita_tatparya` is the Bhāṣya.
  ['गीताप्रस्थानम्','Gītā Prasthāna',['gita_tatparya','gita_bhashya']],
  ['सूत्रप्रस्थानम्','Sūtra Prasthāna',['sutra_bhashya','anu_vyakhyana','nyaya_vivarana','sangraha_bhashya']],
  ['उपनिषत्प्रस्थानम्','Upaniṣat Prasthāna',['ishavasya_bhashya','kathaka_bhashya','atharvana_bhashya','shatprashna_bhashya','manduka_bhashya','aitareya_bhashya','taittiriya_bhashya','kanva_bhashya','chandogya_bhashya','talavakara_bhashya']],
  ['श्रुतिप्रस्थानम्','Śruti Prasthāna',['rg_bhashya']],
  ['इतिहासप्रस्थानम्','Itihāsa Prasthāna',['mbtn','yamaka_bharata']],
  ['पुराणप्रस्थानम्','Purāṇa Prasthāna',['bhagavata_tatparya']],
  ['दशप्रकरणानि','Daśa Prakaraṇāni',['pramana_lakshana','katha_lakshana','tatva_sankhyana','tatva_viveka','tatvodyota','upadhi_khandana','mayavada_khandana','prapancha_mithyatva_khandana','vishnu_tatva_nirnaya','karma_nirnaya']],
  ['स्तोत्रग्रन्थाः','Stotra Granthāḥ',['dvadasha_stotra','parishishta']],
  ['आचारग्रन्थाः','Ācāra Granthāḥ',['sadachara_smriti','krshna_amrta_maharnava','tantrasara_sangraha','yati_pranava_kalpa','jayanti_kalpa','nyasa_paddhati']],
];

// Works the tradition also knows under a second name. Both are shown, primary first, so a
// reader searching for either finds the grantha they expect.
const WALT={
  kanva_bhashya:'बृहदारण्यकभाष्यम्',
  sangraha_bhashya:'अणुभाष्यम्',
};
const wname=(slug,fallback)=>{                       // grantha name in the selected script
  const n=WDEV[slug]?disp(WDEV[slug]):(fallback||slug);
  return WALT[slug] ? `${n} (${disp(WALT[slug])})` : n;
};

function renderHome(){location.hash='';status('');if(window.occClose)occClose();window.scrollTo(0,0);
  const all=Object.fromEntries(q("SELECT slug,title,n_blocks,n_padya,n_topics FROM works").map(w=>[w.slug,w]));
  const card=w=>`<div class="wcard" onclick="location.hash='#/w/${w.slug}'"><div class="t">${wname(w.slug,w.title)}</div>
     <div class="m">${w.n_blocks.toLocaleString()} blocks · ${w.n_padya.toLocaleString()} verses${w.n_topics?` · ${w.n_topics} topics`:''}</div></div>`;
  const seen=new Set(); let html='';
  for(const [dev,en,slugs] of GROUPS){
    const cards=slugs.filter(s=>all[s]).map(s=>{seen.add(s);return card(all[s]);}).join('');
    if(cards)html+=`<div class="grouphd"><span class="gt">${disp(dev)}</span><span class="ge">${en} · ${slugs.filter(s=>all[s]).length}</span></div><div class="works">${cards}</div>`;
  }
  const rest=Object.values(all).filter(w=>!seen.has(w.slug));                 // safety: any uncategorised work
  if(rest.length)html+=`<div class="grouphd"><span class="gt">${disp('अन्ये')}</span><span class="ge">Other · ${rest.length}</span></div><div class="works">${rest.map(card).join('')}</div>`;
  html+=`<div style="text-align:center;margin:26px 0 8px">
    <a class="w-ack" href="#/about" style="display:inline-block">About · Acknowledgement</a></div>`;
  view().innerHTML=hero()+html;
}

// The ācārya, and the line the corpus is named for. ṚV 1.141.3 — मातरिश्वा churns forth him
// who dwells hidden in the cave — read in the sampradāya of Madhva as Vāyu; which is what a
// bhāṣya does to a text, and why it belongs over a library of them.
// Kept as literal Devanāgarī rather than passed through disp(): it is a Vedic citation with
// its own accentuation, and transliterating a scriptural pratīka into eight scripts invites
// exactly the mojibake the svara marks caused elsewhere.
function hero(){return `<div class="hero">
  <div class="hero-t">
    <div class="hero-name">श्रीमदानन्दतीर्थभगवत्पादाचार्यः</div>
    <div class="tag">॥ गुहासन्तं मातरिश्वा मथायति ॥</div>
  </div>
  <img src="img/madhva.jpg" alt="श्रीमदानन्दतीर्थभगवत्पादाचार्यः" width="362" height="425">
</div>`;}

// ── opening page ────────────────────────────────────────────────────────────
// Follows Bhāgavata-VāNi: the ācārya, the name, the invocation, then a script choice before
// entering. It appears only when no script has been stored — a returning reader goes straight
// to the library — and stays reachable at #/about.
const SCRIPTS=[['deva','देवनागरी','Devanāgarī'],['iast','IAST','Roman'],['kn','ಕನ್ನಡ','Kannada'],
               ['te','తెలుగు','Telugu'],['ta','தமிழ்','Tamil'],['ml','മലയാളം','Malayalam'],
               ['bn','বাংলা','Bengali'],['gu','ગુજરાતી','Gujarati']];
function ackHTML(){
  return `<img class="w-pic small" src="img/madhva.jpg" alt="श्रीमदानन्दतीर्थभगवत्पादाचार्यः">
    <h1 class="w-title" style="font-size:28px">सर्वमूलवाणी</h1>
    <div class="w-name">Sarvamūla-VāNi</div>
    <div class="w-script">सर्वमूलग्रन्थाः</div>
    <div class="ack-section"><div class="ack-h">Acknowledgement</div>
      <p>Text content for 36 of the 37 works, along with numbered pramāṇa locations and topic
      headers, has been sourced from the open-source
      <a href="https://setutila.in/" target="_blank" rel="noopener">Setutila</a> project
      (https://setutila.in/). The text content of the Bhāgavata-tātparya-nirṇaya has been
      provided by the Pūrṇaprajña Saṃśodhana Mandiram, Bengaluru.</p></div>
    <div class="ack-section"><div class="ack-h">Developed &amp; maintained by</div>
      <p>Prof. Prathosh<br><a href="mailto:prathoshdata@gmail.com">prathoshdata@gmail.com</a></p></div>
    <div class="ack-section"><div class="ack-h">Recitations</div>
      <p>Chanting synthesized with <a href="https://prathosh.in/vagdhenu/" target="_blank" rel="noopener">Vāgdhenu</a>,
      an open Sanskrit chant text-to-speech system.</p></div>
    <div class="w-invoke">॥ श्रीमध्वपतिः प्रीयताम् ॥</div>`;
}
function renderWelcome(){
  const cards=SCRIPTS.map(([c,native,eng])=>
    `<button class="scriptcard" data-sc="${c}"><span class="sc-native">${native}</span><span class="sc-eng">${eng}</span></button>`).join('');
  view().innerHTML=`<div class="welcome">
    <img class="w-pic" src="img/madhva.jpg" alt="श्रीमदानन्दतीर्थभगवत्पादाचार्यः">
    <h1 class="w-title">सर्वमूलवाणी</h1>
    <div class="w-name">Sarvamūla-VāNi</div>
    <div class="w-script">सर्वमूलग्रन्थाः</div>
    <div class="w-invoke">॥ श्रीमध्वपतिः प्रीयताम् ॥</div>
    <div class="w-credit">Developed &amp; maintained by Prof. Prathosh<br><a href="mailto:prathoshdata@gmail.com">prathoshdata@gmail.com</a></div>
    <div class="w-tts">Recitations created using <a href="https://prathosh.in/vagdhenu/" target="_blank" rel="noopener">Vāgdhenu</a></div>
    <div class="w-prompt">भाषां चिनुत — choose your script</div>
    <div class="scriptlist">${cards}</div>
    <button class="w-ack" id="ackBtn">Acknowledgements</button>
  </div>`;
  status('');
  view().querySelector('.scriptlist').onclick=e=>{
    const b=e.target.closest('[data-sc]'); if(!b) return;
    script=b.dataset.sc; localStorage.setItem('sv_script',script);
    document.getElementById('script').value=script; markScript();
    _welcome=false;
    // The database is 10 MB and may still be arriving; say so rather than showing a blank page.
    if(DB){ location.hash=''; renderHome(); }
    else { view().querySelector('.welcome').insertAdjacentHTML('beforeend','<div class="w-loading">ग्रन्थाः आयान्ति — loading the texts…</div>'); }
  };
  document.getElementById('ackBtn').onclick=()=>{ location.hash='#/about'; };
}
function renderAbout(){
  status('');
  view().innerHTML=`<div class="welcome about"><button class="back-link" id="ackBack">‹</button>${ackHTML()}</div>`;
  document.getElementById('ackBack').onclick=()=>{ if(_welcome){location.hash='';renderWelcome();} else history.back(); };
}

// A work with recitation says so, once, at the top — with the total, a play-from-here and
// (if you have been here before) a resume.

// ── print / save as PDF ───────────────────────────────────────────────────────
// Renders the chosen scope into #printroot and hands off to the browser's print dialog,
// where every platform offers "Save as PDF". No PDF library: none of them shape Devanagari,
// so conjuncts would break — the browser's own text stack is the only one that gets a
// critical edition right. Nothing is uploaded and nothing is fetched; it works offline.
function audioCount(slug){
  try{ return q("SELECT count(*) n FROM audio WHERE work=?",[slug])[0].n; }catch(e){ return 0; }
}
function printDoc(whole){
  const slug=_cache.slug, chaps=_cache.chaps||[];
  if(!slug||!chaps.length) return;
  const w=q("SELECT title FROM works WHERE slug=?",[slug])[0]||{};
  const idx=_cache.chIdx||0;
  const sel = whole ? chaps : [chaps[idx]];
  const body = sel.map(ch=>`<div class="pchap"><div class="ptitle">${disp(ch.title)}</div>`
      + ch.rows.filter((r,i)=>!(i===0&&isHeading(r))).map(block).join('') + `</div>`).join('');
  const scope = whole ? `${chaps.length} अध्यायाः` : disp(chaps[idx].title);
  const root=document.getElementById('printroot');
  root.innerHTML = `<div class="phead">${wname(slug,w.title)}</div>`
    + `<div class="psub">${scope} · सर्वमूलग्रन्थाः</div>` + body
    + `<div class="pfoot">Sarvamūla — ${wname(slug,w.title)}${whole?'':' · '+disp(chaps[idx].title)}</div>`;
  document.body.classList.add('printing');
  // Clear up when printing actually ends. A timer cannot know when the dialog closes: too
  // short and it wipes the document mid-print, too long and it holds state for a minute.
  // onafterprint covers most browsers; matchMedia('print') covers the rest.
  const done=()=>{ document.body.classList.remove('printing'); root.innerHTML=''; };
  // In the iOS/Android apps window.print() is a NO-OP — it is implemented by Mobile Safari and
  // desktop browsers but not by WKWebView or Android WebView, so both PDF buttons did nothing
  // at all, silently, while working on the web. SvPrint hands the WebView to the platform's own
  // print system (PrintManager / UIPrintInteractionController), which is also what keeps
  // Devanagari shaping correct: a JS PDF library places glyphs with no shaping engine and
  // breaks conjuncts. The sheet closing is our cleanup signal, since onafterprint never fires.
  const nat=window.Capacitor&&window.Capacitor.Plugins&&window.Capacitor.Plugins.SvPrint;
  if(nat&&nat.printDoc){
    nat.printDoc({name:wname(slug,w.title)}).then(done,e=>{ done(); status('print: '+(e&&e.message||e)); });
    return;
  }
  window.onafterprint=done;
  if(window.matchMedia){
    const mq=window.matchMedia('print');
    const h=e=>{ if(!e.matches) done(); };
    if(mq.addEventListener) mq.addEventListener('change',h); else if(mq.addListener) mq.addListener(h);
  }
  window.print();
}
window.printDoc=printDoc;

function renderWork(slug,chIdx){
  const _ob=document.getElementById('occbar'); if(_ob)_ob.remove();   // cleared here; re-added by renderBlock if walking
  const w=q("SELECT title FROM works WHERE slug=?",[slug])[0];if(!w)return renderHome();
  if(_cache.slug!==slug){
    const rows=q("SELECT seq,content_type,heading_level,is_padya,pramana,skandha,adhyaya,verse,text_dev,kutra,variants FROM entries WHERE work=? ORDER BY seq",[slug]);
    _cache={slug,chaps:chapters(rows),title:wname(slug,w.title)};
  }
  _cache.chIdx=chIdx; _qwork=null;      // the queue belongs to the open work
  const chaps=_cache.chaps; chIdx=Math.max(0,Math.min(chIdx||0,chaps.length-1));
  const ch=chaps[chIdx]; status('');
  const chapList=chaps.map((c,i)=>`<a class="chap${i===chIdx?' on':''}" onclick="location.hash='#/w/${slug}/${i}'">${disp(c.title)}</a>`).join('');
  const topics=sideTopics(ch);
  const prevNext=`<div class="pn">${chIdx>0?`<a onclick="location.hash='#/w/${slug}/${chIdx-1}'">‹ ${disp(chaps[chIdx-1].title).slice(0,24)}</a>`:'<span></span>'}${chIdx<chaps.length-1?`<a onclick="location.hash='#/w/${slug}/${chIdx+1}'">${disp(chaps[chIdx+1].title).slice(0,24)} ›</a>`:'<span></span>'}</div>`;
  view().innerHTML=`<div class="layout">
    <aside class="nav"><div class="navwork" onclick="location.hash='#/w/${slug}/0'">${wname(slug,w.title)}</div>
      <div class="chaps">${chapList}</div></aside>
    <main class="reader"><div class="ptools">${audioCount(slug)?`<button class="pbtn play" onclick="svStartWork()">▸ पारायणम् · play continuously</button>`:''}<button class="pbtn" onclick="printDoc(false)">PDF: this chapter</button><button class="pbtn" onclick="printDoc(true)">PDF: whole grantha</button></div>${chaps.length>1?`<div class="chtitle">${disp(ch.title)}</div><div class="cmeta">${chIdx+1} / ${chaps.length}</div>`:''}
      ${topics?`<details class="toc-inline"><summary>विषयाः · Topics</summary>${topics}</details>`:''}
      ${ch.rows.filter((r,i)=>!(i===0&&isHeading(r))).map(block).join('')}${prevNext}</main>
    ${topics?`<aside class="toc"><div class="toch">विषयाः · Topics</div>${topics}</aside>`:''}</div>`;
  window.scrollTo(0,0);
}
const SEARCH_PAGE=25;                       // results per page
let searchTerm='', searchToks=[], searchTotal=0, searchPage=0, searchScope='';   // scope = work slug or '' (all)
function searchSetScope(slug){searchScope=slug;renderSearch(searchTerm,0);}
function scopeSelect(id,cur,onchg){
  const works=q("SELECT slug,title FROM works ORDER BY title");
  return `<label class="sscope">in <select onchange="${onchg}(this.value)">
    <option value=""${cur?'':' selected'}>all 38 granthas</option>
    ${works.map(w=>`<option value="${w.slug}"${w.slug===cur?' selected':''}>${w.title}</option>`).join('')}
  </select></label>`;
}
function searchPager(){
  const pages=Math.max(1,Math.ceil(searchTotal/SEARCH_PAGE));
  if(searchTotal<=SEARCH_PAGE) return '';
  return `<div class="pager">
    <button ${searchPage<=0?'disabled':''} onclick="searchGo(-1)">‹ Prev</button>
    <span>${searchPage+1} / ${pages}</span>
    <button ${searchPage>=pages-1?'disabled':''} onclick="searchGo(1)">Next ›</button></div>`;
}
function searchGo(d){
  const pages=Math.max(1,Math.ceil(searchTotal/SEARCH_PAGE));
  const p=Math.max(0,Math.min(searchPage+d,pages-1));
  if(p!==searchPage){renderSearch(searchTerm,p);window.scrollTo(0,0);}
}
function renderSearch(term,page){
  term=(term||'').trim();
  // "quoted" → exact phrase (contiguous, ordered); otherwise all words AND (any order)
  const exact=term.length>=3 && /^["“”].*["“”]$/.test(term);
  const key=norm(exact?term.slice(1,-1):term);if(!key)return renderHome();
  searchTerm=term; searchToks=key.split(' ').filter(Boolean); searchPage=page||0;
  // Back to the top BEFORE rendering, so every exit — results, "no matches", any early return
  // below — lands the reader on the results. Searching from inside a work meant typing while
  // scrolled thousands of pixels down: the results replaced a long chapter with a short list,
  // the scroll position stayed, and the reader was left past the end of the new content
  // looking at blank space. The search only ever *looked* to work on the home page, which is
  // the one page you are already at the top of. renderWork and the pager reset the scroll;
  // Anusandhāna and Anukramaṇikā reset theirs; this path never did.
  window.scrollTo(0,0);
  let where=exact?"text_skel LIKE ?":searchToks.map(()=>"text_skel LIKE ?").join(" AND ");
  let args=exact?['%'+key+'%']:searchToks.map(t=>'%'+t+'%');
  if(searchScope){where=`(${where}) AND work=?`;args=[...args,searchScope];}   // grantha-wise scope
  searchTotal=q(`SELECT COUNT(*) c FROM entries WHERE ${where}`,args)[0].c;
  const pages=Math.max(1,Math.ceil(searchTotal/SEARCH_PAGE));
  if(searchPage>pages-1)searchPage=pages-1;
  const rows=q(`SELECT work,seq,content_type,skandha,adhyaya,verse,text_dev FROM entries WHERE ${where} LIMIT ? OFFSET ?`,
               [...args,SEARCH_PAGE,searchPage*SEARCH_PAGE]);
  const titles=Object.fromEntries(q("SELECT slug,title FROM works").map(r=>[r.slug,r.title]));
  const from=searchTotal?searchPage*SEARCH_PAGE+1:0, to=searchPage*SEARCH_PAGE+rows.length;
  const mode=exact?' · exact phrase':'';
  status(searchTotal?`${from}–${to} of ${searchTotal} for “${term}”${mode}`:`no matches for “${term}”${mode}`);
  const scope=`<div class="scopebar">${scopeSelect('s',searchScope,'searchSetScope')}</div>`;
  if(!searchTotal){view().innerHTML=scope+'<div id="status">no matches'+(searchScope?' in '+(titles[searchScope]||searchScope):'')+'</div>';return;}
  const hits=rows.map(r=>{const ref=[r.skandha,r.adhyaya,r.verse].filter(x=>x!=null).join('.');
    // The matched word, stripped of everything that is not the word. Quotes especially: a hit
    // inside a pramāṇa reads “ब्रह्मजिज्ञासा”, and renderBlock treats a leading “ as a CITATION
    // deep-link, which sets _hlQuote and leaves _hlTerm empty — so nothing was highlighted and,
    // with no .cithit to aim at, the scroll fell back to centring the whole tile and the line
    // ended up off screen. Both complaints, one stray quote mark.
    const hw=(String(r.text_dev||'').split(/[\s।॥]+/).find(w=>{const n=norm(w);return searchToks.some(t=>t&&n.includes(t));})||'')
             .replace(/^[“”‘’"'(\[]+|[“”‘’"',;:.\)\]]+$/g,'').replace(/[।॥ऽ]/g,'');
    return `<a class="v hit" href="#/b/${r.work}/${r.seq}${hw?'/'+encodeURIComponent(hw):''}"><div class="ref">${titles[r.work]||r.work} ${ref}</div><div class="body">${hl(r.text_dev,searchToks)}</div></a>`;}).join('');
  const pager=searchPager();
  view().innerHTML=scope+pager+hits+pager;
}
// deep-link to a specific block (used by Anusandhāna): open the chapter holding seq, scroll + flash it,
// and (if a citation quote is passed) highlight that specific “…” span within the block
function renderBlock(slug,seq,hl){
  // hl (optional) = a “…” citation quote → highlight that span; else a concept word → highlight occurrences
  const isQuote=/^[“‘]/.test(hl||'');
  _hlSeq=(hl?seq:null); _hlQuote=isQuote?hl:''; _hlTerm=(hl&&!isQuote)?hl:'';
  if(_cache.slug!==slug){const rows=q("SELECT seq,content_type,heading_level,is_padya,pramana,skandha,adhyaya,verse,text_dev,kutra,variants FROM entries WHERE work=? ORDER BY seq",[slug]);_cache={slug,chaps:chapters(rows)};}
  let ci=_cache.chaps.findIndex(c=>c.rows.some(r=>r.seq===seq)); if(ci<0)ci=0;
  renderWork(slug,ci);
  _hlSeq=null; _hlQuote=''; _hlTerm='';         // used during the synchronous render; clear now
  showOccBar(slug,seq);                          // synchronous — the block DOM already exists after renderWork
  // An entry recited by another part prints nothing of its own, so #b<seq> may not exist —
  // fall back to the tile that carries its text.
  const el=document.getElementById('b'+seq)||document.getElementById('b'+audioAnchor(seq));
  if(el){
    // Scroll AGAIN once the webfonts are in. The first call runs against system-font metrics,
    // and Devanāgarī reflows hard when SvDeva swaps in — every line above the target changes
    // height, and the target slides out from under the position we just scrolled to. That is
    // the "goes a little ahead": the scroll was right for a layout that lasted one frame.
    const go=()=>{ const t=el.querySelector('.cithit')||el; t.scrollIntoView({block:'center'}); };
    go(); requestAnimationFrame(go);
    if(document.fonts&&document.fonts.ready) document.fonts.ready.then(()=>requestAnimationFrame(go));
    el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1600);}
}
// occurrence walk: step through a concept's loci one by one (set via anuWalk in anusandhana.js)
window.occWalk=null;
function showOccBar(slug,seq){
  let bar=document.getElementById('occbar'); const w=window.occWalk;
  if(!w||w.work!==slug||w.seqs.indexOf(seq)<0){ if(bar)bar.remove(); return; }
  const i=w.seqs.indexOf(seq); w.idx=i;
  if(!bar){ bar=document.createElement('div'); bar.id='occbar'; document.body.appendChild(bar); }
  bar.innerHTML=`<button ${i<=0?'disabled':''} onclick="occGo(-1)">‹ Prev</button>
    <span>${w.term?disp(w.term)+' · ':''}occurrence ${i+1} / ${w.seqs.length}</span>
    <button ${i>=w.seqs.length-1?'disabled':''} onclick="occGo(1)">Next ›</button>
    <button class="occx" onclick="occClose()" title="close">✕</button>`;
}
window.occGo=function(d){const w=window.occWalk;if(!w)return;const i=Math.max(0,Math.min(w.idx+d,w.seqs.length-1));
  location.hash=`#/b/${w.work}/${w.seqs[i]}${w.term?'/'+encodeURIComponent(w.term):''}`;};
window.occClose=function(){window.occWalk=null;const b=document.getElementById('occbar');if(b)b.remove();};
// which top-level tab the current route belongs to; the tab bar is the only place the app
// says where you are, so it is set from the route rather than from the click
function markTab(){const h=location.hash;
  const t=h.startsWith('#/anu')?'anu':h.startsWith('#/idx')?'idx':'read';
  document.querySelectorAll('#tabs .tab').forEach(a=>a.classList.toggle('on',a.dataset.tab===t));}

function route(){const h=location.hash; markTab();
  // The opening page and the acknowledgements read nothing from the database, so they must be
  // routed BEFORE the not-ready guard below — otherwise a first-time visitor stares at
  // "loading…" for the whole 10 MB instead of reading the invocation and picking a script.
  if(h.startsWith('#/about')) return renderAbout();
  if(_welcome) return renderWelcome();
  // Every other view queries the database, and it arrives over the network — there is a window
  // at start-up where a tab can be clicked before it has come. Without this, q() reaches into a
  // null DB and the view reports a bare "Cannot read properties of null". The load handler
  // calls route() again once the data is in, so the click is honoured, just a moment later.
  if(!DB){ status('loading…'); return; }
  if(h.startsWith('#/idx')){const p=h.replace(/^#\/idx\/?/,'').split('/');renderIndex(p[0]||'',p[1]?decodeURIComponent(p[1]):'');}
  else if(h.startsWith('#/anu')){const p=h.replace(/^#\/anu\/?/,'').split('/');renderAnu(p[0]?decodeURIComponent(p[0]):'',p[1]?decodeURIComponent(p[1]):'');}
  else if(h.startsWith('#/b/')){const p=h.slice(4).split('/');renderBlock(decodeURIComponent(p[0]),parseInt(p[1]||'0',10),p[2]?decodeURIComponent(p[2]):'');}
  else if(h.startsWith('#/w/')){const p=h.slice(4).split('/');renderWork(decodeURIComponent(p[0]),parseInt(p[1]||'0',10));}
  else renderHome();}
addEventListener('hashchange',route);
markTab();
document.getElementById('home').onclick=()=>{location.hash='';renderHome();};
// the chosen script drives which shipped face the CSS uses — Telugu and Devanāgarī each
// need one that carries the Vedic marks, since no cluster may span two fonts
function markScript(){document.documentElement.dataset.script=script;checkFace();}
// A Vedic mark missing from the text face does not merely box: the shaper fails on the whole
// cluster and drops neighbouring letters. So a font that failed to load is a CORRECTNESS
// problem, not a cosmetic one — and in a packaged app the usual cause is the .woff2 not being
// copied into the bundle. Say so out loud rather than letting the text quietly lose syllables.
const FACE={deva:'SvDeva',te:'SvTelugu',ml:'SvMlym',bn:'SvBeng',gu:'SvGujr',
            kn:'SvKnda',ta:'SvTaml',pa:'SvGuru',or:'SvOrya'};
function checkFace(){
  const want=FACE[script]; if(!want||!document.fonts||!document.fonts.check) return;
  const go=()=>{ if(!document.fonts.check(`16px '${want}'`))
      status(`font ${want} did not load — Vedic accents will break this script`); };
  document.fonts.ready.then(go).catch(()=>{});
}
markScript();
document.getElementById('script').onchange=e=>{script=e.target.value;localStorage.setItem('sv_script',script);markScript();route();};
// Typing searches after a 200 ms pause; Enter searches at once.
// Enter matters on its own: the box KEEPS its text when you open a grantha, and an `input`
// event only fires when the value actually changes — so pressing Enter on a word already
// sitting there did nothing at all, while retyping the same word worked. Anything that leaves
// text in the box (navigating into a work, coming back from a hit) needs a way to re-run it.
let qt;
function runSearch(){
  clearTimeout(qt);
  const t=(document.getElementById('q').value||'').trim();
  t.length>=2 ? renderSearch(t) : route();
}
document.getElementById('q').oninput=e=>{clearTimeout(qt);const t=e.target.value.trim();qt=setTimeout(()=>{t.length>=2?renderSearch(t):route();},200);};
document.getElementById('q').onkeydown=e=>{ if(e.key==='Enter'){ e.preventDefault(); runSearch(); } };
// reading font size (persisted, applied to --read; mūla scales relative)
// A−/A+ wrote sv_read even while nothing visible was bound to --read, so presses made
// during that period were stored unseen and would all apply at once now that the binding is
// fixed. Those were never really chosen; discard them once. Anything set from here is kept.
if(localStorage.getItem('sv_readv')!=='2'){ localStorage.removeItem('sv_read'); localStorage.setItem('sv_readv','2'); }
let readPx=parseInt(localStorage.getItem('sv_read')||'19',10);
function applyRead(){readPx=Math.max(15,Math.min(28,readPx));document.documentElement.style.setProperty('--read',readPx+'px');localStorage.setItem('sv_read',readPx);}
applyRead();
document.getElementById('fsUp').onclick=()=>{readPx++;applyRead();};
document.getElementById('fsDown').onclick=()=>{readPx--;applyRead();};
// Palette: the default warm-paper scheme, or the brighter one defined in index.html. Set on
// <html> so it costs one attribute and no re-render, and remembered like the script choice.
let palette=localStorage.getItem('sv_palette')||'';
function applyPalette(){
  if(palette) document.documentElement.dataset.palette=palette;
  else delete document.documentElement.dataset.palette;
  const b=document.getElementById('palBtn');
  if(b){ b.classList.toggle('on',palette==='bright');
         b.title=palette==='bright'?'back to the softer palette':'brighter palette'; }
}
applyPalette();
document.getElementById('palBtn').onclick=()=>{
  palette = palette==='bright' ? '' : 'bright';
  localStorage.setItem('sv_palette',palette); applyPalette();
};
// The DB is 40 MB and the browser caches it hard. Every audio bake rewrites it, so a stale
// copy silently shows a work as having no audio — which is exactly how Viṣṇutattvanirṇaya
// looked "not assembled" when its 178 files were on disk and serving. DB_REV busts it;
// bump on any rebuild. (serve.py's no-store headers do not reach an already-cached copy.)
const DB_REV='2026-08-18a';
// The database comes from R2, not from the bundle. It is 50 MB and we re-bake it whenever a
// work is re-rendered; shipping it inside the iOS/Android binaries would mean a store review
// for every content fix. Fetched, a correction is one upload. `sv_db` overrides the host, the
// same way `sv_audio` overrides the audio base, so a local build can be tested against
// web/sarvamula.db.
//
// Caching is DELIBERATE. This used to pass {cache:'no-store'}, which re-downloaded all 50 MB
// on every single page load — a mobile reader would have paid for it every time they opened
// the app. DB_REV is in the URL, so a new database is a new URL and the old copy can never be
// served in its place; there is nothing left for no-store to protect against.
const DB_HOST=(localStorage.getItem('sv_db')||'https://pub-f4f244dc7f1b4ad2ad5c4116104064ed.r2.dev')
              .replace(/\/+$/,'');
// ── content revisions come from the NETWORK, not the bundle ───────────────────────────────
// The iOS/Android apps ship these two constants inside the binary, so every text or audio
// correction stopped at the web: the reader kept requesting …/sarvamula.db?v=<old rev> and its
// own cache answered. Three fixes in one day never reached an installed app for that reason.
// version.json is small and fetched no-store, so a re-bake reaches every device on next launch
// and a content fix no longer needs a store review.
//
// Offline is preserved by falling back, in order: last revisions seen (localStorage) → the
// constants above. A device that has never been online still opens with the bundled revision
// and its cached database; one that has been online keeps reading the copy it already holds.
let AUDIO_REV_LIVE=AUDIO_REV, DB_REV_LIVE=DB_REV;
async function revisions(){
  try{
    const r=await fetch(DB_HOST+'/version.json',{cache:'no-store'});
    if(r.ok){
      const j=await r.json();
      if(j && j.db && j.audio){ localStorage.setItem('sv_rev',JSON.stringify(j)); return j; }
    }
  }catch(e){}                                    // offline, or the object is not there yet
  try{
    const j=JSON.parse(localStorage.getItem('sv_rev')||'null');
    if(j && j.db && j.audio) return j;
  }catch(e){}
  return {db:DB_REV,audio:AUDIO_REV};
}
initSqlJs({locateFile:f=>f})
  .then(async SQL=>{
    const rev=await revisions();
    DB_REV_LIVE=rev.db; AUDIO_REV_LIVE=rev.audio;
    return SQL;
  })
  .then(SQL=>fetch(DB_HOST+'/sarvamula.db?v='+DB_REV_LIVE)
                .then(r=>{ if(!r.ok) throw new Error(`${r.status} fetching the database`);
                                     return r.arrayBuffer(); })
  .then(buf=>{DB=new SQL.Database(new Uint8Array(buf));document.getElementById('script').value=script;
              // If they are still choosing a script, leave the opening page alone and let their
              // click take them in; routing here would yank the page out from under them.
              if(_welcome && !location.hash.startsWith('#/about')) return;
              route();}))
  .catch(e=>status('load error: '+e.message));
// The opening page needs no data, so paint it immediately rather than after a 10 MB download.
if(_welcome && !location.hash.startsWith('#/about')) renderWelcome();
