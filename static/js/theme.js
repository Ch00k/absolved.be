// The page's theme: the one picked with the theme button, kept in this browser, or else the device's,
// followed as it changes. A classic script in <head>, run before the page is drawn, so it never shows
// in the wrong theme.

const THEME_KEY = "theme";
// Each tap on the button moves to the next pick, back to the device's after dark.
const THEME_PICKS = ["system", "light", "dark"];
// The browser's bar in the colour of the page under it.
const THEME_COLOURS = { light: "#fafaf9", dark: "#0c0a09" };
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

// Storage can be refused, as in some private windows; the pick then lasts until the page is closed.
let pickedTheme = "system";
try {
  const stored = localStorage.getItem(THEME_KEY);
  if (THEME_PICKS.includes(stored)) {
    pickedTheme = stored;
  }
} catch {
  // The device's theme is followed.
}

// The pick is set on the root element too, for the button to show its icon.
function applyTheme() {
  const theme = pickedTheme === "system" ? (systemDark.matches ? "dark" : "light") : pickedTheme;
  document.documentElement.dataset.themePick = pickedTheme;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = THEME_COLOURS[theme];
}

applyTheme();
systemDark.addEventListener("change", applyTheme);

function labelThemeButton(button) {
  const label = button.dataset[`label${pickedTheme[0].toUpperCase()}${pickedTheme.slice(1)}`];
  button.setAttribute("aria-label", label);
  button.title = label;
}

document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("theme-button");
  labelThemeButton(button);
  button.addEventListener("click", () => {
    pickedTheme = THEME_PICKS[(THEME_PICKS.indexOf(pickedTheme) + 1) % THEME_PICKS.length];
    try {
      localStorage.setItem(THEME_KEY, pickedTheme);
    } catch {
      // Kept for this page only.
    }
    applyTheme();
    labelThemeButton(button);
  });
});
