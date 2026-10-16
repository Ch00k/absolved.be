// What the forms that post with a script share: the new-password rule, the CSRF token, and how they report
// progress and errors.

// The password field carries the minimum length the server renders; counted in characters, as a person counts
// them, where the browser's own minlength check counts UTF-16 units.
export function longEnough(password) {
  return [...password.value].length >= password.minLength;
}

// Why a new password and its repetition cannot be used, or null when they can.
export function newPasswordProblem(form) {
  const password = form.querySelector("[data-password]");
  if (!longEnough(password)) {
    return form.dataset.tooShort;
  }
  if (form.querySelector("[data-password-confirmation]").value !== password.value) {
    return form.dataset.mismatch;
  }
  return null;
}

// Read from the cookie when the request is sent: logging in, in another tab too, replaces the token a page was
// rendered with.
export function csrfToken() {
  return document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "";
}

// What the server said went wrong. Its own errors are JSON; anything else, such as an error page, says only that
// something did.
export async function errorMessage(form, response) {
  if (response.headers.get("Content-Type")?.startsWith("application/json")) {
    return (await response.json()).error;
  }
  return form.dataset.unexpected;
}

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
