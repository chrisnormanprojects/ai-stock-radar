const CACHE = 'ai-stock-radar-v10';
const ASSETS = ['./','./index.html','./manifest.webmanifest','./assets/icon-180.png','./assets/icon-192.png','./assets/icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('ai-stock-radar-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // Data fallback is explicitly labelled by the app; never substitute HTML.
  if (url.pathname.includes('/data/')) {
    event.respondWith(fetch(event.request, {cache:'no-store'}));
    return;
  }
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(async response => {
      if (response.ok) {const cache = await caches.open(CACHE); await cache.put('./index.html', response.clone());}
      return response;
    }).catch(async () => (await caches.open(CACHE)).match('./index.html')));
  } else {
    event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
  }
});
