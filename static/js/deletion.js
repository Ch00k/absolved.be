// Deleting the account: the password confirms it, as the login key derived from it, and once the server has
// deleted the account nothing of it stays on this device either, neither the key nor the copies of pages.

import { goToLogin } from "./examination.js";
import { csrfToken, errorMessage, feedback } from "./forms.js";
import { deriveKeys, forgetKey } from "./keys.js";
import { forgetPages } from "./offline.js";

const form = document.querySelector("[data-account-deletion]");
const { fail, busy } = feedback(form);

async function deleteAccount(username, password) {
  const { authKey } = await deriveKeys(username, password);
  const body = new FormData();
  body.set("csrfmiddlewaretoken", csrfToken());
  body.set("auth_key", authKey);
  const response = await fetch(form.action, { method: "POST", body });
  // The session ended, and the server sent the request to its login page.
  if (response.redirected) {
    return goToLogin();
  }
  if (!response.ok) {
    return fail(await errorMessage(form, response));
  }

  const { next } = await response.json();
  await Promise.allSettled([forgetKey(), forgetPages()]);
  location.assign(next);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  busy(true);
  try {
    await deleteAccount(document.body.dataset.username, form.querySelector("[data-current-password]").value);
  } catch {
    fail(form.dataset.failed);
  } finally {
    busy(false);
  }
});
