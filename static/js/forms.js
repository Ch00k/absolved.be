// What the forms that derive keys share: the password rule, and how they report progress and errors.

// Anyone holding a copy of the database can guess passwords offline, so a short one is what would
// expose an examination. Counted in characters, as a person counts them.
export const MIN_PASSWORD_LENGTH = 12;

export function feedback(form) {
  const error = form.querySelector("[data-form-error]");
  const button = form.querySelector('button:not([type="button"])');
  const label = button.innerHTML;

  return {
    fail(message) {
      error.textContent = message;
      error.hidden = false;
    },
    // Deriving keys takes a moment, several seconds where WebAssembly is unavailable.
    busy(on) {
      button.disabled = on;
      if (on) {
        error.hidden = true;
        button.textContent = button.dataset.busyLabel;
      } else {
        button.innerHTML = label;
      }
    },
  };
}
