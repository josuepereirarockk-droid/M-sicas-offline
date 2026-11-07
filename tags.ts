// Leitura de tags (título, artista, álbum, capa, letra, ReplayGain) de MP3, M4A, FLAC, OGG e Opus.
// Funciona na página e dentro do Web Worker (usa só Blob, DataView e TextDecoder).
interface Cover { mime: string; bytes: Uint8Array }
interface Tags { title?: string; artist?: string; album?: string; lyrics?: string; rg?: number; cover?: Cover }
interface LrcLine { t: number; l: string }

function parseGain(v: string): number | undefined {
  const m = /(-?\d+(?:[.,]\d+)?)/.exec(v);
  return m ? parseFloat(m[1].replace(',', '.')) : undefined;
}

function parseID3(buf: ArrayBuffer | null): Tags | null {
  if (!buf) return null;
  const d = new Uint8Array(buf);
  if (d.length < 10 || String.fromCharCode(d[0], d[1], d[2]) !== 'ID3') return null;
  const ver = d[3];
  const ss = (b: Uint8Array, o: number): number => (b[o] << 21) | (b[o + 1] << 14) | (b[o + 2] << 7) | b[o + 3];
  const dec = (b: Uint8Array, e: number): string => {
    try {
      let c = e === 0 ? 'iso-8859-1' : e === 1 ? 'utf-16' : e === 2 ? 'utf-16be' : 'utf-8';
      if (e === 1 && b[0] === 0xfe && b[1] === 0xff) c = 'utf-16be';
      return new TextDecoder(c).decode(b).replace(/\0+$/, '').trim();
    } catch { return ''; }
  };
  // posição depois de um texto terminado em nulo (1 ou 2 bytes, conforme a codificação)
  const skipText = (f: Uint8Array, p: number, e: number): number => {
    if (e === 1 || e === 2) { while (p + 1 < f.length && !(f[p] === 0 && f[p + 1] === 0)) p += 2; return p + 2; }
    while (p < f.length && f[p] !== 0) p++;
    return p + 1;
  };
  let o = 10;
  const end = Math.min(d.length, 10 + ss(d, 6));
  if (d[5] & 0x40) o += ver === 4 ? ss(d, 10) : (((d[10] << 24) | (d[11] << 16) | (d[12] << 8) | d[13]) + 4);
  const r: Tags = {};
  while (o + 10 <= end) {
    const id = String.fromCharCode(d[o], d[o + 1], d[o + 2], d[o + 3]);
    if (!/^[A-Z0-9]{4}$/.test(id)) break;
    const sz = ver === 4 ? ss(d, o + 4) : ((d[o + 4] << 24) | (d[o + 5] << 16) | (d[o + 6] << 8) | d[o + 7]);
    if (sz <= 0 || o + 10 + sz > d.length) break;
    const f = d.subarray(o + 10, o + 10 + sz), e = f[0];
    if (id === 'TIT2') r.title = dec(f.subarray(1), e);
    else if (id === 'TPE1') r.artist = dec(f.subarray(1), e);
    else if (id === 'TALB') r.album = dec(f.subarray(1), e);
    else if (id === 'USLT') r.lyrics = dec(f.subarray(skipText(f, 4, e)), e);
    else if (id === 'TXXX') {
      const p = skipText(f, 1, e);
      const name = dec(f.subarray(1, p), e);
      if (/replaygain_track_gain/i.test(name)) { const g = parseGain(dec(f.subarray(p), e)); if (g !== undefined) r.rg = g; }
    } else if (id === 'APIC' && !r.cover) {
      let p = 1;
      while (p < f.length && f[p] !== 0) p++;
      const mime = dec(f.subarray(1, p), 0);
      p = skipText(f, p + 2, e);
      if (p < f.length) r.cover = { mime: mime || 'image/jpeg', bytes: f.slice(p) };
    }
    o += 10 + sz;
  }
  return r;
}

function parseMP4(buf: ArrayBuffer): Tags {
  const d = new Uint8Array(buf), v = new DataView(buf), r: Tags = {};
  const tp = (o: number): string => String.fromCharCode(d[o], d[o + 1], d[o + 2], d[o + 3]);
  const dec = (x: Uint8Array): string => new TextDecoder().decode(x);
  type Fn = (t: string, s: number, e: number) => void;
  function at(s: number, e: number, fn: Fn): void {
    while (s + 8 <= e) {
      const sz = v.getUint32(s), t = tp(s + 4);
      if (sz < 8 || s + sz > e) break;
      fn(t, s + 8, s + sz);
      s += sz;
    }
  }
  at(0, d.length, (t, s, e) => { if (t === 'moov') at(s, e, (t, s, e) => { if (t === 'udta') at(s, e, (t, s, e) => {
    if (t === 'meta') at(s + 4, e, (t, s, e) => { if (t === 'ilst') at(s, e, (k, s, e) => {
      let nm = '';
      at(s, e, (t, s2, e2) => {
        if (t === 'name') { nm = dec(d.subarray(s2 + 4, e2)); return; }
        if (t !== 'data') return;
        const pl = d.subarray(s2 + 8, e2);
        if (k === '\xa9nam') r.title = dec(pl);
        else if (k === '\xa9ART') r.artist = dec(pl);
        else if (k === '\xa9alb') r.album = dec(pl);
        else if (k === '\xa9lyr') r.lyrics = dec(pl);
        else if (k === '----' && /replaygain_track_gain/i.test(nm)) { const g = parseGain(dec(pl)); if (g !== undefined) r.rg = g; }
        else if (k === 'covr' && !r.cover) r.cover = { mime: (v.getUint32(s2) & 0xffffff) === 14 ? 'image/png' : 'image/jpeg', bytes: pl.slice() };
      });
    }); });
  }); }); });
  return r;
}

function parseFLAC(buf: ArrayBuffer): Tags | null {
  const d = new Uint8Array(buf), v = new DataView(buf);
  if (d.length < 8 || String.fromCharCode(d[0], d[1], d[2], d[3]) !== 'fLaC') return null;
  const r: Tags = {};
  let o = 4, last = false;
  while (!last && o + 4 <= d.length) {
    const h = d[o];
    last = !!(h & 128);
    const t = h & 127, len = (d[o + 1] << 16) | (d[o + 2] << 8) | d[o + 3];
    o += 4;
    if (o + len > d.length) break;
    if (t === 4) {
      let p = o;
      p += 4 + v.getUint32(p, true);
      let n = v.getUint32(p, true);
      p += 4;
      while (n-- > 0 && p + 4 <= o + len) {
        const l = v.getUint32(p, true);
        p += 4;
        const c = new TextDecoder().decode(d.subarray(p, p + l));
        p += l;
        const i = c.indexOf('=');
        if (i > 0) {
          const k = c.slice(0, i).toUpperCase(), x = c.slice(i + 1);
          if (k === 'TITLE') r.title = x;
          else if (k === 'ARTIST') r.artist = x;
          else if (k === 'ALBUM') r.album = x;
          else if (k === 'LYRICS' || k === 'UNSYNCEDLYRICS') r.lyrics = x;
          else if (k === 'REPLAYGAIN_TRACK_GAIN') { const g = parseGain(x); if (g !== undefined) r.rg = g; }
        }
      }
    } else if (t === 6 && !r.cover) {
      let p = o + 4;
      const ml = v.getUint32(p);
      p += 4;
      const mime = new TextDecoder().decode(d.subarray(p, p + ml));
      p += ml;
      const dl = v.getUint32(p);
      p += 4 + dl + 16;
      const il = v.getUint32(p);
      p += 4;
      if (p + il <= d.length) r.cover = { mime: mime || 'image/jpeg', bytes: d.slice(p, p + il) };
    }
    o += len;
  }
  return r;
}

function parseOGG(buf: ArrayBuffer): Tags | null {
  const d = new Uint8Array(buf), v = new DataView(buf);
  if (d.length < 27 || String.fromCharCode(d[0], d[1], d[2], d[3]) !== 'OggS') return null;
  const find = (pat: number[]): number => {
    for (let i = 0; i + pat.length <= d.length; i++) {
      let k = 0;
      while (k < pat.length && d[i + k] === pat[k]) k++;
      if (k === pat.length) return i;
    }
    return -1;
  };
  let p = -1;
  const opus = find([0x4f, 0x70, 0x75, 0x73, 0x54, 0x61, 0x67, 0x73]); // "OpusTags"
  if (opus >= 0) p = opus + 8;
  else {
    const vb = find([0x03, 0x76, 0x6f, 0x72, 0x62, 0x69, 0x73]); // 0x03 + "vorbis"
    if (vb >= 0) p = vb + 7;
  }
  if (p < 0 || p + 8 > d.length) return null;
  const r: Tags = {};
  p += 4 + v.getUint32(p, true);
  if (p + 4 > d.length) return null;
  let n = v.getUint32(p, true);
  p += 4;
  while (n-- > 0 && p + 4 <= d.length) {
    const l = v.getUint32(p, true);
    p += 4;
    if (p + l > d.length) break;
    const c = new TextDecoder().decode(d.subarray(p, p + l));
    p += l;
    const i = c.indexOf('=');
    if (i > 0) {
      const k = c.slice(0, i).toUpperCase(), x = c.slice(i + 1);
      if (k === 'TITLE') r.title = x;
      else if (k === 'ARTIST') r.artist = x;
      else if (k === 'ALBUM') r.album = x;
      else if (k === 'LYRICS' || k === 'UNSYNCEDLYRICS') r.lyrics = x;
      else if (k === 'REPLAYGAIN_TRACK_GAIN') { const g = parseGain(x); if (g !== undefined) r.rg = g; }
    }
  }
  return r;
}

function parseLRC(txt: string): LrcLine[] | null {
  const out: LrcLine[] = [];
  for (const ln of txt.split(/\r?\n/)) {
    const ts = [...ln.matchAll(/\[(\d+):(\d+(?:\.\d+)?)\]/g)];
    if (!ts.length) continue;
    const l = ln.replace(/\[[^\]]*\]/g, '').trim();
    ts.forEach(m => out.push({ t: +m[1] * 60 + +m[2], l }));
  }
  return out.length >= 2 ? out.sort((x, y) => x.t - y.t) : null;
}

async function readHead(f: Blob): Promise<ArrayBuffer | null> {
  const h = new Uint8Array(await f.slice(0, 10).arrayBuffer());
  if (String.fromCharCode(h[0], h[1], h[2]) !== 'ID3') return null;
  return f.slice(0, Math.min(((h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9]) + 10, 12e6)).arrayBuffer();
}

async function readMP4(f: Blob): Promise<Tags | null> {
  let o = 0;
  while (o + 16 <= f.size) {
    const h = new DataView(await f.slice(o, o + 16).arrayBuffer());
    let sz = h.getUint32(0);
    const t = String.fromCharCode(h.getUint8(4), h.getUint8(5), h.getUint8(6), h.getUint8(7));
    if (sz === 1) sz = Number(h.getBigUint64(8));
    if (sz < 8) return null;
    if (t === 'moov') return parseMP4(await f.slice(o, Math.min(o + sz, o + 25e6)).arrayBuffer());
    o += sz;
  }
  return null;
}

async function readTags(f: File): Promise<Tags | null> {
  const n = (f.name || '').toLowerCase();
  try {
    if (/\.(m4a|mp4)$/.test(n)) return await readMP4(f);
    if (n.endsWith('.flac')) return parseFLAC(await f.slice(0, Math.min(f.size, 10e6)).arrayBuffer());
    if (/\.(ogg|opus|oga)$/.test(n)) return parseOGG(await f.slice(0, Math.min(f.size, 512e3)).arrayBuffer());
    return parseID3(await readHead(f));
  } catch { return null; }
}
