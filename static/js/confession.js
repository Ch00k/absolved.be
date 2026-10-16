// The confession page: shows only the statements the decrypted examination marks, their details, and its notes.

import { openExamination, reveal } from "./examination.js";

const container = document.getElementById("examination");
const { examination } = await openExamination(container.dataset.ciphertext);

const marked = new Set(examination.statements);
for (const statement of container.querySelectorAll("[data-statement]")) {
  const id = statement.dataset.statement;
  statement.hidden = !marked.has(id);

  const details = statement.querySelector("[data-details]");
  const text = examination.details[id] ?? "";
  details.querySelector("span").textContent = text;
  details.hidden = !text.trim();
}
for (const question of container.querySelectorAll("[data-question]")) {
  question.hidden = !question.querySelector("[data-statement]:not([hidden])");
}

const notes = container.querySelector("[data-notes]");
notes.textContent = examination.notes;
notes.hidden = !examination.notes.trim();

container.querySelector("[data-nothing-marked]").hidden = Boolean(
  container.querySelector("[data-question]:not([hidden]), [data-notes]:not([hidden])"),
);
reveal(container);
