// The keys of a user's account, derived from their username and password in the browser.
//
// Argon2id (libsodium) turns the password into a master key; HKDF (WebCrypto) splits that into the
// key sent to the server in place of the password, and the key that encrypts the examination. The
// encryption key is created non-extractable: the browser uses it but never hands its bytes to any
// script, and it is kept in IndexedDB until logout.
//
// Changing any constant here changes every user's keys, which locks them out of their account and
// makes their examination unreadable.

const SALT_PREFIX = "absolved.be:";
// libsodium's "interactive" limits, fixed here so that a libsodium release cannot change them.
const ARGON2_PASSES = 2;
const ARGON2_MEMORY_BYTES = 64 * 1024 * 1024;

const DATABASE = "absolved";
const STORE = "keys";
const SLOT = "examination";

const encoder = new TextEncoder();

function hex(buffer) {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// libsodium's scripts are loaded with defer ahead of the page's modules, so they have run by now;
// `ready` settles once its WebAssembly, or its plain JavaScript fallback, is initialised.
async function sodium() {
  await globalThis.sodium.ready;
  return globalThis.sodium;
}

// Usernames are lowercase ASCII, the same however they are typed. Passwords are normalised, since
// devices can encode the same accented letter in two ways.
export async function deriveKeys(username, password) {
  const libsodium = await sodium();
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(SALT_PREFIX + username));
  const salt = new Uint8Array(digest, 0, libsodium.crypto_pwhash_SALTBYTES);

  const master = libsodium.crypto_pwhash(
    32,
    password.normalize("NFC"),
    salt,
    ARGON2_PASSES,
    ARGON2_MEMORY_BYTES,
    libsodium.crypto_pwhash_ALG_ARGON2ID13,
  );
  const material = await crypto.subtle.importKey("raw", master, "HKDF", false, ["deriveBits", "deriveKey"]);
  master.fill(0);

  const hkdf = (info) => ({ name: "HKDF", hash: "SHA-256", salt: new Uint8Array(), info: encoder.encode(info) });
  const authKey = await crypto.subtle.deriveBits(hkdf("auth"), material, 256);
  const encryptionKey = await crypto.subtle.deriveKey(
    hkdf("examination"),
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );

  return { authKey: hex(authKey), encryptionKey };
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(mode, operation) {
  const database = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const request = operation(database.transaction(STORE, mode).objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    database.close();
  }
}

export function storeKey(username, encryptionKey) {
  return withStore("readwrite", (store) => store.put({ username, encryptionKey }, SLOT));
}

// The key is kept with the username it belongs to, so a key left behind by another account on this
// device is never used.
export async function loadKey(username) {
  const entry = await withStore("readonly", (store) => store.get(SLOT));
  return entry?.username === username ? entry.encryptionKey : null;
}

export function forgetKey() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DATABASE);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    // Another tab holding the database open delays the deletion until it closes; the key is
    // unreachable for this page either way.
    request.onblocked = () => resolve();
  });
}
