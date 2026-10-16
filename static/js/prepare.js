// The prepare page: fills the questionnaire from the decrypted examination, and encrypts and saves it
// shortly after every change.

import { goToLogin, openExamination, reveal } from "./examination.js";
import { csrfToken } from "./forms.js";
import { seal } from "./seal.js";

// How long typing has to pause before the examination is saved.
const SAVE_DELAY_MS = 800;
// A weak signal can leave a save hanging; after this long it counts as failed, and the saves after it go ahead.
const SAVE_TIMEOUT_MS = 15_000;

const form = document.getElementById("examination");
const status = form.querySelector("[data-save-status]");
const statements = form.querySelectorAll("[data-statement]");
const notes = form.querySelector("textarea[data-notes]");

function setNotesOpen(statement, open) {
  statement.querySelector("[data-notes-toggle]").setAttribute("aria-expanded", String(open));
}

// A statement's notes open where it has some, and a question with several statements opens where one of
// them is marked.
function fill(examination) {
  const marked = new Set(examination.statements);
  for (const statement of statements) {
    const id = statement.dataset.statement;
    const text = examination.details[id] ?? "";
    statement.querySelector('input[name="statement"]').checked = marked.has(id);
    statement.querySelector("textarea[data-details]").value = text;
    setNotesOpen(statement, text !== "");
  }
  for (const question of form.querySelectorAll("details[data-question]")) {
    question.open = Boolean(question.querySelector('input[name="statement"]:checked'));
  }
  notes.value = examination.notes;
}

// A statement's notes are kept only while it is marked.
function read() {
  const marked = [];
  const details = {};
  for (const statement of statements) {
    if (!statement.querySelector('input[name="statement"]').checked) {
      continue;
    }

    const id = statement.dataset.statement;
    marked.push(id);
    const text = statement.querySelector("textarea[data-details]").value;
    if (text.trim()) {
      details[id] = text;
    }
  }
  return { statements: marked, details, notes: notes.value };
}

// The notes icon opens a statement's notes field, ready to type in, and closes it again.
form.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-notes-toggle]");
  if (!toggle) {
    return;
  }

  const statement = toggle.closest("[data-statement]");
  const open = toggle.getAttribute("aria-expanded") !== "true";
  setNotesOpen(statement, open);
  if (open) {
    statement.querySelector("textarea[data-details]").focus();
  }
});

const { key, examination } = await openExamination(form.dataset.ciphertext);
fill(examination);
reveal(form);

// The server takes this page's saves while the examination is still the version the page opened, or this page
// saved it last; otherwise it changed elsewhere since, and this page's copy is out of date.
const page = crypto.randomUUID();

// Every change is encrypted as it is made, so that the latest is ready to send at once, even from a page that is
// closing. Encryptions run one after another, so an older change never replaces a newer one.
let unsent = null;
let sealing = Promise.resolve();
// Saves run one after another, so an older examination never lands after a newer one.
let saving = Promise.resolve(true);
let timer = null;
let sending = 0;
let failed = false;
let stale = false;

// "Saved" only once the latest change is.
function showStatus() {
  if (stale) {
    status.textContent = form.dataset.stale;
  } else if (sending) {
    status.textContent = form.dataset.saving;
  } else if (timer || unsent) {
    status.textContent = "";
  } else {
    status.textContent = failed ? form.dataset.failed : form.dataset.saved;
  }
}

function saveRequest(ciphertext) {
  const body = new FormData();
  body.set("csrfmiddlewaretoken", csrfToken());
  body.set("opened_version", form.dataset.openedVersion);
  body.set("page", page);
  body.set("ciphertext", ciphertext);
  return body;
}

// Sends the latest change, if there is one. Resolves to whether the examination is saved.
async function save() {
  const ciphertext = unsent;
  unsent = null;
  if (stale || ciphertext === null) {
    showStatus();
    return !failed;
  }

  sending += 1;
  showStatus();
  const response = await fetch(form.dataset.saveUrl, {
    method: "POST",
    body: saveRequest(ciphertext),
    signal: AbortSignal.timeout(SAVE_TIMEOUT_MS),
  }).catch(() => null);
  sending -= 1;

  // The session ended, and the server sent the request to its login page.
  if (response?.redirected) {
    return goToLogin();
  }

  stale ||= response?.status === 409;
  failed = response?.status !== 204;
  showStatus();
  return !failed;
}

function saveNow() {
  clearTimeout(timer);
  timer = null;
  saving = saving.then(async () => {
    await sealing;
    return save();
  });
  return saving;
}

form.addEventListener("input", () => {
  const current = read();
  sealing = sealing.then(async () => {
    unsent = await seal(key, current);
  });
  clearTimeout(timer);
  timer = setTimeout(saveNow, SAVE_DELAY_MS);
  showStatus();
});

// A phone may close a page put in the background, and a page being left is about to close: the latest change goes
// out at once, as a beacon, which outlives the page. A page that lives on saves it again as usual, to learn whether
// it was saved.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && unsent !== null && !stale) {
    navigator.sendBeacon(form.dataset.saveUrl, saveRequest(unsent));
  }
});

// Saves even an untouched examination, which is what lets Confession open.
form.querySelector("[data-ready]").addEventListener("click", async () => {
  await sealing;
  unsent = await seal(key, read());
  if (await saveNow()) {
    location.assign(form.dataset.confessionUrl);
  }
});
