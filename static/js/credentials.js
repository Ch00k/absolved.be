// Signup and login: derives the keys from the password, posts the login key in place of the password,
// and keeps the encryption key only once the server has accepted the login key. The pages kept for
// offline use are forgotten then, since they may belong to the account that was here before.

import { csrfToken, errorMessage, feedback, newPasswordProblem } from "./forms.js";
import { deriveKeys, storeKey } from "./keys.js";
import { forgetPages } from "./offline.js";

const form = document.querySelector("[data-credentials]");
const { fail, busy } = feedback(form);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = form.elements.username.value.trim().toLowerCase();
  const password = form.querySelector("[data-password]").value;
  const problem = form.dataset.credentials === "signup" ? newPasswordProblem(form) : null;
  if (problem) {
    return fail(problem);
  }

  busy(true);
  try {
    const { authKey, encryptionKey } = await deriveKeys(username, password);
    const body = new FormData(form);
    body.set("csrfmiddlewaretoken", csrfToken());
    body.set("username", username);
    body.set("auth_key", authKey);
    const response = await fetch(form.action, { method: "POST", body });
    if (!response.ok) {
      return fail(await errorMessage(form, response));
    }

    const { next } = await response.json();
    await Promise.all([storeKey(username, encryptionKey), forgetPages()]);
    location.assign(next);
  } catch {
    fail(form.dataset.failed);
  } finally {
    busy(false);
  }
});
