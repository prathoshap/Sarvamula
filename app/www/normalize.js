
(function(g){
  const CONS={"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "s", "ष": "s", "स": "s", "ह": "h", "ळ": "l", "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "फ़": "f"}, VOWELS={"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "r", "ॠ": "r", "ऌ": "l", "ॡ": "l", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऄ": "e", "ऒ": "o"}, MATRA={"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "r", "ॄ": "r", "ॢ": "l", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o"};
  const OFFSETS=[[2432, 2559, 128], [2560, 2687, 256], [2688, 2815, 384], [2816, 2943, 512], [2944, 3071, 640], [3072, 3199, 768], [3200, 3327, 896], [3328, 3455, 1024]], ASPIRATE=[["kh", "k"], ["gh", "g"], ["ch", "c"], ["jh", "j"], ["th", "t"], ["dh", "d"], ["ph", "p"], ["bh", "b"]];
  const VIRAMA='्', ANUSVARA='ं', VISARGA='ः', CANDRA='ँ',
        AVAGRAHA='ऽ', NUKTA='़', ZWJ='‍', ZWNJ='‌';
  function scriptToDev(s){
    let out='';
    for(const ch of s){ const o=ch.codePointAt(0);
      if(o>=0x0900&&o<=0x097F){ out+=ch; continue; }
      let hit=false;
      for(const [lo,hi,off] of OFFSETS){ if(o>=lo&&o<=hi){ out+=String.fromCodePoint(o-off); hit=true; break; } }
      if(!hit) out+=ch;
    } return out;
  }
  function devToAscii(text){
    let out=[], pend=false;
    for(const ch of text){
      if(CONS[ch]!==undefined){ if(pend)out.push('a'); out.push(CONS[ch]); pend=true; }
      else if(MATRA[ch]!==undefined){ out.push(MATRA[ch]); pend=false; }
      else if(ch===VIRAMA){ pend=false; }
      else if(VOWELS[ch]!==undefined){ if(pend){out.push('a');pend=false;} out.push(VOWELS[ch]); }
      else if(ch===ANUSVARA||ch===CANDRA){ if(pend){out.push('a');pend=false;} out.push('m'); }
      else if(ch===VISARGA){ if(pend){out.push('a');pend=false;} out.push('h'); }
      else if(ch===AVAGRAHA||ch===NUKTA||ch===ZWJ||ch===ZWNJ){ continue; }
      else { if(pend){out.push('a');pend=false;} out.push(' '); }
    }
    if(pend)out.push('a');
    return out.join('').replace(/\s+/g,' ').trim();
  }
  function asciiToSkel(a){
    let s=a.toLowerCase();
    s=s.replace(/ee|ii/g,'i').replace(/oo|uu/g,'u').replace(/aa/g,'a');
    s=s.split('sh').join('s').split('ri').join('r');
    for(const [x,y] of ASPIRATE) s=s.split(x).join(y);
    s=s.replace(/[aeiou]/g,'');
    s=s.replace(/(.)\1+/g,'$1');
    return s.replace(/\s+/g,' ').trim();
  }
  function romanFold(q){ return q.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase(); }
  function normalizeQuery(q){
    let ascii;
    if([...q].some(c=>{const o=c.codePointAt(0);return o>=0x0900&&o<=0x0DFF;}))
      ascii=devToAscii(scriptToDev(q));
    else ascii=romanFold(q);
    return [ascii, asciiToSkel(ascii)];
  }
  g.BhagNorm={scriptToDev,devToAscii,asciiToSkel,romanFold,normalizeQuery};
  if(typeof module!=='undefined') module.exports=g.BhagNorm;
})(typeof window!=='undefined'?window:globalThis);

(function(g){
  const ADD={kn:0x380,te:0x300,ml:0x400,bn:0x080,gu:0x180,pa:0x100,or:0x200,ta:0x280};
  const IV={'अ':'a','आ':'ā','इ':'i','ई':'ī','उ':'u','ऊ':'ū',
    'ऋ':'ṛ','ॠ':'ṝ','ऌ':'ḷ','ए':'e','ऐ':'ai','ओ':'o','औ':'au'};
  const MV={'ा':'ā','ि':'i','ी':'ī','ु':'u','ू':'ū',
    'ृ':'ṛ','े':'e','ै':'ai','ो':'o','ौ':'au'};
  const CV={'क':'k','ख':'kh','ग':'g','घ':'gh','ङ':'ṅ','च':'c','छ':'ch',
    'ज':'j','झ':'jh','ञ':'ñ','ट':'ṭ','ठ':'ṭh','ड':'ḍ',
    'ढ':'ḍh','ण':'ṇ','त':'t','थ':'th','द':'d','ध':'dh','न':'n',
    'प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l',
    'व':'v','श':'ś','ष':'ṣ','स':'s','ह':'h','ळ':'ḷ'};
  function toIast(t){
    let out=[],pend=false;
    for(const ch of t){
      if(CV[ch]!==undefined){ if(pend)out.push('a'); out.push(CV[ch]); pend=true; }
      else if(MV[ch]!==undefined){ out.push(MV[ch]); pend=false; }
      else if(ch==='्'){ pend=false; }
      else if(IV[ch]!==undefined){ if(pend){out.push('a');pend=false;} out.push(IV[ch]); }
      else if(ch==='ं'||ch==='ँ'){ if(pend){out.push('a');pend=false;} out.push('ṃ'); }
      else if(ch==='ः'){ if(pend){out.push('a');pend=false;} out.push('ḥ'); }
      else if(ch==='़'||ch==='‍'||ch==='‌'){ }
      else if(ch==='ऽ'){ if(pend){out.push('a');pend=false;} out.push('’'); }
      // Vedic accents in ROMAN text must become Latin combining diacritics. Passing the
      // Devanāgarī codepoints through leaves U+0951/U+0952/U+1CDA sitting over Latin letters,
      // where no roman font has them and every accent shows as a box. These are the marks the
      // Vedic transliteration convention uses: acute for udātta, macron-below for anudātta,
      // double-acute for the double svarita.
      else if(ch==='\u0951'){ if(pend){out.push('a');pend=false;} out.push('\u0301'); }
      else if(ch==='\u0952'){ if(pend){out.push('a');pend=false;} out.push('\u0331'); }
      else if(ch==='\u0953'){ if(pend){out.push('a');pend=false;} out.push('\u0300'); }
      else if(ch==='\u0954'){ if(pend){out.push('a');pend=false;} out.push('\u030D'); }
      else if(ch==='\u1CDA'){ if(pend){out.push('a');pend=false;} out.push('\u030B'); }
      // daṇḍa has no glyph in most roman faces either; the transliteration convention is |, ||
      // Devanāgarī digits in a verse reference (॥ ६/४॥) are not roman either
      else if(ch>='\u0966'&&ch<='\u096F'){ if(pend){out.push('a');pend=false;}
        out.push(String.fromCharCode(48+ch.charCodeAt(0)-0x0966)); }
      else if(ch==='\u0964'){ if(pend){out.push('a');pend=false;} out.push('|'); }
      else if(ch==='\u0965'){ if(pend){out.push('a');pend=false;} out.push('||'); }
      else { if(pend){out.push('a');pend=false;} out.push(ch); }
    }
    if(pend)out.push('a');
    return out.join('');
  }
  // per-script letter merges where the offset slot is unassigned: Bengali has no retroflex
  // LLA and no distinct VA → map to LA / BA (Bengali doesn't distinguish v from b).
  const PATCH={0x080:{'ळ':'ল','व':'ব'}};
  function toScript(t,add){
    const px=PATCH[add]||null;
    let out='';
    for(const ch of t){ const o=ch.codePointAt(0);
      if(o===0x200d||o===0x200c) continue;   // drop ZWJ/ZWNJ — Devanāgarī half-forms must
                                              // become natural conjuncts (ottu) in other scripts
      if(o===0x0950){                         // ॐ: dedicated glyph only in Gujarati(ૐ)/Tamil;
        out += (add===0x180) ? String.fromCodePoint(o+add)        // Gujarati ૐ via offset
             : String.fromCodePoint(0x0913+add)+String.fromCodePoint(0x0902+add);  // else spell ओ+ं
        continue; }
      if(px && px[ch]!==undefined){ out+=px[ch]; continue; }
      // U+0951-0954 are the VEDIC TONE MARKS (udātta, anudātta, svarita). They are not
      // script-specific letters and have no counterpart at the offset: 0x0952+0x380 is
      // U+0CD2, unassigned in Kannada, so every accent became a tofu box — U+0C52 in Telugu,
      // and so on for each script. They pass through unchanged, exactly as the Vedic
      // Extensions marks (U+1CDA and friends) already do.
      if(o>=0x0951&&o<=0x0954){ out+=ch; continue; }
      if((o>=0x0900&&o<=0x0963)||(o>=0x0966&&o<=0x097F)) out+=String.fromCodePoint(o+add);
      else out+=ch; }
    return out;
  }
  // Tamil's Unicode block is sparse (no voiced/aspirated stops, no vocalic-ṛ sign),
  // so the offset map yields tofu. Collapse to the standard Tamil rendering of Sanskrit:
  // unvoiced-unaspirated base letters + Grantha (ஜ ஶ ஷ ஸ ஹ) + aytham ஃ for visarga.
  const T_IV={'अ':'அ','आ':'ஆ','इ':'இ','ई':'ஈ','उ':'உ','ऊ':'ஊ','ऋ':'ரி','ॠ':'ரீ','ऌ':'லி','ए':'ஏ','ऐ':'ஐ','ओ':'ஓ','औ':'ஔ'};
  const T_MV={'ा':'ா','ि':'ி','ी':'ீ','ु':'ு','ू':'ூ','ृ':'்ரி','ॄ':'்ரீ','ॢ':'்லி','े':'ே','ै':'ை','ो':'ோ','ौ':'ௌ'};
  const T_CV={'क':'க','ख':'க','ग':'க','घ':'க','ङ':'ங','च':'ச','छ':'ச','ज':'ஜ','झ':'ஜ','ञ':'ஞ','ट':'ட','ठ':'ட','ड':'ட','ढ':'ட','ण':'ண','त':'த','थ':'த','द':'த','ध':'த','न':'ந','प':'ப','फ':'ப','ब':'ப','भ':'ப','म':'ம','य':'ய','र':'ர','ल':'ல','व':'வ','श':'ஶ','ष':'ஷ','स':'ஸ','ह':'ஹ','ळ':'ள','ऩ':'ன','ऱ':'ற','ऴ':'ழ'};
  function toTamil(t){
    let out='',base=null;
    const flush=()=>{ if(base!==null){out+=base;base=null;} };
    for(const ch of t){ const o=ch.codePointAt(0);
      if(T_CV[ch]!==undefined){ flush(); base=T_CV[ch]; }
      else if(T_MV[ch]!==undefined){ if(base!==null){out+=base+T_MV[ch];base=null;} else out+=T_MV[ch]; }
      else if(ch==='्'){ if(base!==null){out+=base+'்';base=null;} }
      else if(T_IV[ch]!==undefined){ flush(); out+=T_IV[ch]; }
      else if(ch==='ं'||ch==='ँ'){ flush(); out+='ம்'; }
      else if(ch==='ः'){ flush(); out+='ஃ'; }
      else if(ch==='ॐ'){ flush(); out+='ௐ'; }
      else if(ch==='ऽ'){ flush(); out+='’'; }
      else if(ch==='़'||ch==='‍'||ch==='‌'){ }
      else if(o>=0x0966&&o<=0x096F){ flush(); out+=String(o-0x0966); }
      else { flush(); out+=ch; }
    }
    flush();
    return out;
  }
  g.BhagDisplay=function(dev,lang){
    if(lang==='deva') return dev;
    if(lang==='iast') return toIast(dev);
    if(lang==='ta') return toTamil(dev);
    return ADD[lang]!==undefined ? toScript(dev,ADD[lang]) : dev;
  };
})(typeof window!=='undefined'?window:globalThis);
