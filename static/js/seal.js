// Encrypts a value for the server to store, and decrypts what it returns: AES-GCM with a fresh
// 12-byte nonce for every save, carried in front of the ciphertext, all in base64.

const NONCE_BYTES = 12;

function toBase64(bytes) {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function fromBase64(text) {
  return Uint8Array.from(atob(text), (character) => character.charCodeAt(0));
}

export async function seal(key, value) {
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, plaintext));

  const sealed = new Uint8Array(NONCE_BYTES + ciphertext.length);
  sealed.set(nonce);
  sealed.set(ciphertext, NONCE_BYTES);
  return toBase64(sealed);
}

// Rejects when the key is not the one the value was sealed with.
export async function unseal(key, text) {
  const sealed = fromBase64(text);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: sealed.subarray(0, NONCE_BYTES) },
    key,
    sealed.subarray(NONCE_BYTES),
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}
