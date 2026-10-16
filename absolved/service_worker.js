// Keeps a copy of every page and file of this site as it is fetched, so that what was last opened
// still opens without a connection: a church often has none. The network is tried first, except for
// a file whose name carries a hash of its contents, which never changes under that name.

const CACHE = "absolved";
// A weak signal can leave a request hanging; after this long the kept copy is shown instead.
const NETWORK_WAIT_MS = 4000;
// How production names static files: a hash of the contents before the extension. Copies of older
// versions are kept too, since the pages kept before a deploy still ask for them.
const HASHED_STATIC_FILE = /^\/static\/.*\.[0-9a-f]{12}\.[^./]+$/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// Keeping copies is best effort: a full disk must not cost a page the network's answer.
async function keep(request, response) {
  try {
    const cache = await caches.open(CACHE);
    // A redirect means the page was not served, as when the session has ended, so its copy is out of date. A page
    // opened in the browser gets the redirect itself, as an opaque one; a fetch from a script follows it.
    if (response.redirected || response.type === "opaqueredirect") {
      await cache.delete(request);
    } else if (response.ok) {
      await cache.put(request, response);
    }
  } catch {
    // The copy stays as it was.
  }
}

async function keptCopy(request) {
  try {
    return await caches.match(request, { ignoreVary: true });
  } catch {
    return undefined;
  }
}

async function networkFirst(event) {
  const { request } = event;
  const network = fetch(request);
  // Copied before the page reads the answer, and kept even when the page was given the kept copy meanwhile.
  event.waitUntil(network.then((response) => keep(request, response.clone())).catch(() => {}));

  try {
    const response = await Promise.race([network, new Promise((resolve) => setTimeout(resolve, NETWORK_WAIT_MS))]);
    if (response) {
      return response;
    }
  } catch {
    // Offline: the kept copy follows.
  }

  return (await keptCopy(request)) ?? network;
}

async function cacheFirst(event) {
  const kept = await keptCopy(event.request);
  if (kept) {
    return kept;
  }

  const response = await fetch(event.request);
  event.waitUntil(keep(event.request, response.clone()));
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  // A request sent by a page as it closes, such as a beacon, would be lost with the page if left to it, so the
  // worker sends it itself.
  if (request.keepalive) {
    event.respondWith(fetch(request));
  } else if (request.method === "GET") {
    event.respondWith(HASHED_STATIC_FILE.test(url.pathname) ? cacheFirst(event) : networkFirst(event));
  }
});
