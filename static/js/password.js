// Changing the password: the examination is decrypted with the current password's key and encrypted
// again with the new one, and the server replaces the login key and the examination together. The
// pages kept for offline use then carry an examination the new key cannot open, so they are forgotten.

import { goToLogin } from "./examination.js";
import { csrfToken, errorMessage, feedback, newPasswordProblem } from "./forms.js";
import { deriveKeys, storeKey } from "./keys.js";
import { forgetPages } from "./offline.js";
import { seal, unseal } from "./seal.js";

const form = document.querySelector("[data-password-change]");
const success = form.querySelector("[data-form-success]");
const { fail, busy } = feedback(form);
// Lets the server tell this page's changes from those made elsewhere since the page was opened.
const page = crypto.randomUUID();

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
  body.set("csrfmiddlewaretoken", csrfToken());
  body.set("old_auth_key", current.authKey);
  body.set("new_auth_key", next.authKey);
  body.set("ciphertext", ciphertext);
  body.set("opened_version", form.dataset.openedVersion);
  body.set("page", page);
  const response = await fetch(form.action, { method: "POST", body });
  // The session ended, and the server sent the request to its login page.
  if (response.redirected) {
    return goToLogin();
  }
  if (response.status !== 204) {
    return fail(await errorMessage(form, response));
  }

  await Promise.all([storeKey(username, next.encryptionKey), forgetPages()]);
  form.dataset.ciphertext = ciphertext;
  form.reset();
  success.textContent = form.dataset.changed;
  success.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  success.hidden = true;

  const problem = newPasswordProblem(form);
  if (problem) {
    return fail(problem);
  }

  busy(true);
  try {
    await change(
      document.body.dataset.username,
      form.querySelector("[data-current-password]").value,
      form.querySelector("[data-password]").value,
    );
  } catch {
    fail(form.dataset.failed);
  } finally {
    busy(false);
  }
});
