// Keeps a copy of every page and file of this site as it is fetched, so that what was last opened
// still opens without a connection: a church often has none. The network is always tried first.

const CACHE = "absolved";
// A weak signal can leave a request hanging; after this long the kept copy is shown instead.
const NETWORK_WAIT_MS = 4000;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  const network = fetch(request).then(async (response) => {
    // A redirect means the page was not served, as when the session has ended.
    if (response.ok && !response.redirected) {
      await cache.put(request, response.clone());
    }
    return response;
  });

  try {
    const response = await Promise.race([network, new Promise((resolve) => setTimeout(resolve, NETWORK_WAIT_MS))]);
    if (response) {
      return response;
    }
  } catch {
    // Offline: the kept copy follows.
  }

  return (await cache.match(request, { ignoreVary: true })) ?? network;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  event.respondWith(networkFirst(request));
});
