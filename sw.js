// 네트워크 우선: 항상 최신 소식을 받고, 오프라인일 때만 저장해 둔 화면을 보여줘요.
const CACHE="hanwha-notes-v5";
const CORE=["./","./index.html","./clips.json","./manifest.webmanifest","./icon-192.png","./eagles-emblem.png"];
self.addEventListener("install",e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener("fetch",e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=="GET"||u.origin!==location.origin)return;
  // 브라우저 HTTP 캐시(최대 10분)를 건너뛰고 서버에 새 버전이 있는지 매번 확인해요
  e.respondWith(fetch(e.request.url,{cache:"no-cache",credentials:"same-origin"}).then(r=>{const cp=r.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));return r}).catch(()=>caches.match(e.request,{ignoreSearch:true}).then(r=>r||caches.match("./index.html"))));
});

// 커뮤니티 새 글 알림
self.addEventListener("push",e=>{
  let d={};try{d=e.data?e.data.json():{}}catch(_){d={title:"이글스 라운지",body:e.data&&e.data.text()}}
  e.waitUntil(self.registration.showNotification(d.title||"이글스 라운지",{body:d.body||"",icon:"icon-192.png",badge:"icon-192.png",tag:d.tag,renotify:!!d.tag,data:{url:d.url||"./#board"}}));
});
self.addEventListener("notificationclick",e=>{
  e.notification.close();
  const url=new URL(e.notification.data&&e.notification.data.url||"./#board",self.registration.scope).href;
  e.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(ws=>{
    for(const w of ws){if(w.url.startsWith(self.registration.scope)&&"focus" in w){w.navigate(url);return w.focus()}}
    return clients.openWindow(url);
  }));
});
