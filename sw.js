const C='musicas-v19',F=['./','index.html','manifest.json','icon.svg','icon-192.png','icon-512.png','icon-maskable-512.png','apple-touch-icon.png','bg-butterfly.jpg','bg-city-top.jpg','bg-city-char.jpg','tags.js','tags-worker.js'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(F)))});
self.addEventListener('message',e=>{if(e.data==='skip')self.skipWaiting()});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!=='inbox').map(x=>caches.delete(x)))).then(()=>clients.claim())));
async function share(e){try{const fd=await e.request.formData(),files=fd.getAll('audio').filter(f=>f&&f.name),c=await caches.open('inbox');let i=0;
 for(const f of files)await c.put(new Request(new URL('./inbox/'+Date.now()+'-'+(i++)+'-'+encodeURIComponent(f.name),self.registration.scope).href),new Response(f,{headers:{'content-type':f.type||'application/octet-stream'}}))}catch(_){}
 return Response.redirect(new URL('./?inbox=1',self.registration.scope).href,303)}
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method==='POST'&&u.pathname.endsWith('/share')){e.respondWith(share(e));return}
 if(e.request.method!=='GET')return;e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));return r}).catch(()=>caches.match(e.request)))});
