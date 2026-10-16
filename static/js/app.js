// What every page does: counts the time since dates, keeps date inputs to the device's today, shows a
// picked date and opens the calendar for it, opens dialogs, shows a password on request, approves a new password and its repetition, forgets the key on
// logout, and installs the service worker that keeps pages for offline use.

import { MIN_PASSWORD_LENGTH } from "./forms.js";
import { forgetKey } from "./keys.js";
import { describeSince, formatDate, localDate } from "./since.js";

const today = localDate();

for (const time of document.querySelectorAll("time[data-since]")) {
  time.textContent = describeSince(time.dateTime, today, time.dataset.since, document.documentElement.lang);
}

// A count of days under a time already given in days would only repeat it.
for (const detail of document.querySelectorAll("[data-since-detail]")) {
  const days = detail.querySelector("time").textContent;
  detail.hidden = Array.from(document.querySelectorAll('time[data-since="natural"]')).some(
    (time) => time.textContent === days,
  );
}

// The server's today can be a day behind or ahead of the device's.
for (const input of document.querySelectorAll("input[data-not-after-today]")) {
  input.max = today;
}
for (const input of document.querySelectorAll("input[data-default-today]")) {
  input.value = today;
}

// A date picker shows its input's date. A desktop browser opens its calendar only from its own small
// button, which the invisible input hides, so a click anywhere on the picker opens it.
for (const picker of document.querySelectorAll("[data-date-picker]")) {
  const input = picker.querySelector("input");
  const text = picker.querySelector("[data-date-text]");
  const show = () => {
    text.textContent = input.value ? formatDate(input.value, document.documentElement.lang) : picker.dataset.empty;
  };
  show();
  input.addEventListener("input", show);
  input.addEventListener("click", () => input.showPicker?.());
}

for (const dialog of document.querySelectorAll("dialog[data-modal]")) {
  dialog.showModal();
}

for (const button of document.querySelectorAll("button[data-reveal-password]")) {
  button.addEventListener("click", () => {
    const shown = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(shown));
    button.closest(".password-field").querySelector("input").type = shown ? "text" : "password";
  });
}

// A new password is approved once it is long enough, and its repetition once the two match; the stylesheet
// ticks an approved field. The browser's own minlength check cannot stand in: it stops applying once a
// script changes the field, as the eye button does, and it counts UTF-16 units where people count characters.
for (const repetition of document.querySelectorAll("input[data-password-confirmation]")) {
  const password = repetition.form.querySelector("input[data-password]");
  repetition.form.addEventListener("input", () => {
    password.toggleAttribute("data-approved", [...password.value].length >= MIN_PASSWORD_LENGTH);
    repetition.toggleAttribute("data-approved", repetition.value !== "" && repetition.value === password.value);
  });
  // A reset empties both fields.
  repetition.form.addEventListener("reset", () => {
    password.removeAttribute("data-approved");
    repetition.removeAttribute("data-approved");
  });
}

// The copies of pages kept for offline use; there are none where the browser offers no cache storage.
async function forgetPages() {
  if (globalThis.caches) {
    await Promise.all((await caches.keys()).map((name) => caches.delete(name)));
  }
}

// Logging out, or deleting the account, leaves nothing of the account on this device: neither the
// key nor the copies of pages, which carry the encrypted examination.
for (const form of document.querySelectorAll("form[data-forget-key]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await Promise.allSettled([forgetKey(), forgetPages()]);
    form.submit();
  });
}

navigator.serviceWorker?.register(document.body.dataset.serviceWorkerUrl);
