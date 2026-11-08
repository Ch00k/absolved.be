// The size of the confession page's script, picked with its two buttons and kept in this browser. A classic script
// in <head>, run before the page is drawn, so it never shows at the wrong size.

const TEXT_SIZE_KEY = "confession-text-size";
// How much the script is zoomed at each size; the buttons move between neighbours.
const TEXT_SIZES = [1, 1.25, 1.5, 1.75, 2];

// Storage can be refused, as in some private windows; the size then lasts until the page is closed.
let textSize = 0;
try {
  const stored = Number(localStorage.getItem(TEXT_SIZE_KEY));
  if (Number.isInteger(stored) && TEXT_SIZES[stored]) {
    textSize = stored;
  }
} catch {
  // The script is shown at its own size.
}

function applyTextSize() {
  document.documentElement.style.setProperty("--text-zoom", TEXT_SIZES[textSize]);
}

applyTextSize();

document.addEventListener("DOMContentLoaded", () => {
  const smaller = document.getElementById("text-smaller");
  const larger = document.getElementById("text-larger");

  function update(step) {
    const focused = document.activeElement;
    textSize = Math.min(Math.max(textSize + step, 0), TEXT_SIZES.length - 1);
    try {
      localStorage.setItem(TEXT_SIZE_KEY, textSize);
    } catch {
      // Kept for this page only.
    }

    applyTextSize();
    smaller.disabled = textSize === 0;
    larger.disabled = textSize === TEXT_SIZES.length - 1;

    // A button disabled while it has focus drops it to the page; the other button takes it, so that a keyboard or
    // screen reader user keeps their place.
    if (focused?.disabled) {
      (focused === smaller ? larger : smaller).focus();
    }
  }

  smaller.addEventListener("click", () => update(-1));
  larger.addEventListener("click", () => update(1));
  update(0);
});
