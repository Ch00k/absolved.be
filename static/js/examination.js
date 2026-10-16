// The examination as the browser holds it once decrypted:
// { statements: [ids of the marked statements], details: { [statement id]: text }, notes: text }.

import { loadKey } from "./keys.js";
import { unseal } from "./seal.js";

const EMPTY = { statements: [], details: {}, notes: "" };

function goToLogin() {
  const login = new URL(document.body.dataset.loginUrl, location.href);
  login.searchParams.set("next", location.pathname);
  location.assign(login);
  // The page is leaving; nothing after this should run.
  return new Promise(() => {});
}

// The key and the decrypted examination. A device without the key, or with one that does not open
// the examination, is sent to log in, which derives the key again.
export async function openExamination(ciphertext) {
  const key = await loadKey(document.body.dataset.username);
  if (!key) {
    return goToLogin();
  }

  if (!ciphertext) {
    return { key, examination: EMPTY };
  }

  try {
    return { key, examination: await unseal(key, ciphertext) };
  } catch {
    return goToLogin();
  }
}

// Shows the element, which is rendered hidden until the examination has been decrypted.
export function reveal(element) {
  document.querySelector("[data-unlocking]").hidden = true;
  element.hidden = false;
}
