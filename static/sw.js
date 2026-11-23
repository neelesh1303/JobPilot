// JobPilot service worker: makes the app open instantly.
// - The app shell ("/") and static files are served from cache straight away, then refreshed in the background,
//   so a sleeping server never shows a blank "waking up" screen.
// - Job data is NOT cached here (the page keeps its own last copy and always refreshes it from the server).
const CACHE = "jobpilot-v3";
const SHELL = ["/", "/static/icon-192.png", "/static/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function cacheFirst(req, cacheKey) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(cacheKey || req);
  const update = fetch(req).then((res) => {
    // only keep real pages (not the login redirect or an error page)
    if (res.ok && !res.redirected) cache.put(cacheKey || req, res.clone());
    return res;
  });
  if (hit) { update.catch(() => {}); return hit; }
  return update;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin) {
    if (req.mode === "navigate" && url.pathname === "/") return e.respondWith(cacheFirst(req, "/"));
    if (url.pathname.startsWith("/static/") && !url.pathname.endsWith(".apk")) return e.respondWith(cacheFirst(req));
    return; // API, resumes, login: always network
  }
  // fonts and the PDF viewer from CDNs never change for a given URL
  if (/fonts\.(googleapis|gstatic)\.com|cdnjs\.cloudflare\.com/.test(url.host)) e.respondWith(cacheFirst(req));
});
