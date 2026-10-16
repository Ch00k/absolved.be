// The copies of pages the service worker keeps for offline use.

// There are none where the browser offers no cache storage.
export async function forgetPages() {
  if (globalThis.caches) {
    await Promise.all((await caches.keys()).map((name) => caches.delete(name)));
  }
}
