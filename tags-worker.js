"use strict";
importScripts('tags.js');
const wk = self;
wk.onmessage = async (e) => {
    const { id, file } = e.data;
    let t = null;
    try {
        t = await readTags(file);
    }
    catch {
        t = null;
    }
    try {
        wk.postMessage({ id, t }, t && t.cover ? [t.cover.bytes.buffer] : []);
    }
    catch {
        wk.postMessage({ id, t: null });
    }
};
