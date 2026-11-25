/**
 * Light / Dark mode controller syncing localStorage, prefers-color-scheme, and toggle controls.
 */

const STORAGE_KEY = "vcraft-theme";
const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";
const TRANSITION_CLASS = "theme-transition";
const TRANSITION_DURATION_MS = 260;

let transitionTimerId = null;

function getStoredTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null;
  }
}

function saveTheme(theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}

function resolveInitialDark(mediaQuery) {
  const stored = getStoredTheme();
  if (stored !== null) {
    return stored === "dark";
  }
  return mediaQuery.matches;
}

function applyTheme(isDark, { animate = false } = {}) {
  const root = document.documentElement;
  if (animate) {
    if (transitionTimerId !== null) {
      window.clearTimeout(transitionTimerId);
    }
    root.classList.add(TRANSITION_CLASS);
    // Force style flush so transitions start from the previous palette cleanly.
    void root.offsetWidth;
  }

  root.classList.toggle("dark", isDark);
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-pressed", String(isDark));
  });

  if (animate) {
    transitionTimerId = window.setTimeout(() => {
      root.classList.remove(TRANSITION_CLASS);
      transitionTimerId = null;
    }, TRANSITION_DURATION_MS);
  }
}

function initThemeToggle() {
  const mediaQuery = window.matchMedia(DARK_MEDIA_QUERY);
  applyTheme(resolveInitialDark(mediaQuery));

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextDark = !document.documentElement.classList.contains("dark");
      saveTheme(nextDark ? "dark" : "light");
      applyTheme(nextDark, { animate: true });
    });
  });

  mediaQuery.addEventListener("change", (event) => {
    if (getStoredTheme() === null) {
      applyTheme(event.matches, { animate: true });
    }
  });
}

initThemeToggle();
