// The prepare page: fills the questionnaire from the decrypted examination, and encrypts and saves it
// shortly after every change.

import { openExamination, reveal } from "./examination.js";
import { seal } from "./seal.js";

// How long typing has to pause before the examination is saved.
const SAVE_DELAY_MS = 800;

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

async function save() {
  status.textContent = form.dataset.saving;

  const body = new FormData();
  body.set("csrfmiddlewaretoken", form.elements.csrfmiddlewaretoken.value);
  body.set("ciphertext", await seal(key, read()));
  const response = await fetch(form.dataset.saveUrl, { method: "POST", body }).catch(() => null);

  // The session ended, and the server sent the request to its login page.
  if (response?.redirected) {
    location.assign(response.url);
    return false;
  }

  const saved = response?.status === 204;
  status.textContent = saved ? form.dataset.saved : form.dataset.failed;
  return saved;
}

// Saves run one after another, so an older examination never lands after a newer one.
let saving = Promise.resolve(true);
let timer = null;

function saveNow() {
  clearTimeout(timer);
  timer = null;
  saving = saving.then(save, save);
  return saving;
}

function saveSoon() {
  clearTimeout(timer);
  timer = setTimeout(saveNow, SAVE_DELAY_MS);
}

form.addEventListener("input", saveSoon);

// A phone may close a page put in the background, so a pending save goes out at once.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && timer) {
    saveNow();
  }
});

form.querySelector("[data-ready]").addEventListener("click", async () => {
  if (await saveNow()) {
    location.assign(form.dataset.confessionUrl);
  }
});
