/* My AI Pro service worker: offline shell only - chat and API always live. */
var CACHE = 'myaipro-shell-v1';
var SHELL = ['/', '/static/manifest.webmanifest', '/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) return;                 // chat, billing, usage: always network
  if (url.pathname === '/' || url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(CACHE).then(function (c) {
        return fetch(e.request).then(function (res) {           // network-first, cache fallback
          if (res.ok) c.put(e.request, res.clone());
          return res;
        }).catch(function () { return c.match(e.request); });
      })
    );
  }
});
