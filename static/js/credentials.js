// Signup and login: derives the keys from the password, posts the login key in place of the password,
// and keeps the encryption key only once the server has accepted the login key.

import { feedback, MIN_PASSWORD_LENGTH } from "./forms.js";
import { deriveKeys, storeKey } from "./keys.js";

const form = document.querySelector("[data-credentials]");
const { fail, busy } = feedback(form);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = form.elements.username.value.trim().toLowerCase();
  const password = form.querySelector("[data-password]").value;
  if (form.dataset.credentials === "signup") {
    if ([...password].length < MIN_PASSWORD_LENGTH) {
      return fail(form.dataset.tooShort);
    }
    if (form.querySelector("[data-password-confirmation]").value !== password) {
      return fail(form.dataset.mismatch);
    }
  }

  busy(true);
  try {
    const { authKey, encryptionKey } = await deriveKeys(username, password);
    const body = new FormData(form);
    body.set("username", username);
    body.set("auth_key", authKey);
    const response = await fetch(form.action, { method: "POST", body });
    const result = await response.json();
    if (!response.ok) {
      return fail(result.error);
    }

    await storeKey(username, encryptionKey);
    location.assign(result.next);
  } catch {
    fail(form.dataset.failed);
  } finally {
    busy(false);
  }
});
