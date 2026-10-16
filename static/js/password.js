// Changing the password: the examination is decrypted with the current password's key and encrypted
// again with the new one, and the server replaces the login key and the examination together.

import { feedback, MIN_PASSWORD_LENGTH } from "./forms.js";
import { deriveKeys, storeKey } from "./keys.js";
import { seal, unseal } from "./seal.js";

const form = document.querySelector("[data-password-change]");
const success = form.querySelector("[data-form-success]");
const { fail, busy } = feedback(form);

async function change(username, currentPassword, newPassword) {
  const current = await deriveKeys(username, currentPassword);
  const next = await deriveKeys(username, newPassword);

  let ciphertext = "";
  if (form.dataset.ciphertext) {
    let examination;
    try {
      examination = await unseal(current.encryptionKey, form.dataset.ciphertext);
    } catch {
      return fail(form.dataset.wrongPassword);
    }
    ciphertext = await seal(next.encryptionKey, examination);
  }

  const body = new FormData();
  body.set("csrfmiddlewaretoken", form.elements.csrfmiddlewaretoken.value);
  body.set("old_auth_key", current.authKey);
  body.set("new_auth_key", next.authKey);
  body.set("ciphertext", ciphertext);
  const response = await fetch(form.action, { method: "POST", body });
  if (response.status !== 204) {
    return fail((await response.json()).error);
  }

  await storeKey(username, next.encryptionKey);
  form.dataset.ciphertext = ciphertext;
  form.reset();
  success.textContent = form.dataset.changed;
  success.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  success.hidden = true;

  const newPassword = form.querySelector("[data-password]").value;
  if ([...newPassword].length < MIN_PASSWORD_LENGTH) {
    return fail(form.dataset.tooShort);
  }
  if (form.querySelector("[data-password-confirmation]").value !== newPassword) {
    return fail(form.dataset.mismatch);
  }

  busy(true);
  try {
    await change(document.body.dataset.username, form.querySelector("[data-current-password]").value, newPassword);
  } catch {
    fail(form.dataset.failed);
  } finally {
    busy(false);
  }
});
