// Web Worker: lê as tags em segundo plano para o app não travar ao importar centenas de músicas.
declare function importScripts(...urls: string[]): void;
importScripts('tags.js');
const wk = self as unknown as { onmessage: (e: MessageEvent) => void; postMessage: (m: unknown, t?: Transferable[]) => void };
wk.onmessage = async (e: MessageEvent<{ id: number; file: File }>) => {
  const { id, file } = e.data;
  let t: Tags | null = null;
  try { t = await readTags(file); } catch { t = null; }
  try { wk.postMessage({ id, t }, t && t.cover ? [t.cover.bytes.buffer] : []); }
  catch { wk.postMessage({ id, t: null }); }
};
