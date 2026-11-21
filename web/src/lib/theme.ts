/**
 * Light / dark theme. The user picks light, dark, or system; system (the
 * default) follows the OS appearance, live. Whatever is picked lands on
 * <html data-theme="light|dark">, which is the only thing index.css reads.
 *
 * index.html sets the attribute with the same rule in an inline script before
 * first paint, so a dark-theme user never sees a white flash. Keep the two in
 * step (STORAGE_KEY and the media query).
 */
export type Theme = "light" | "dark";
export type ThemePref = Theme | "system";

const STORAGE_KEY = "sarai.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function loadThemePref(): ThemePref {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

export function saveThemePref(pref: ThemePref): void {
  if (pref === "system") localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, pref);
}

export function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

/** Calls `onChange` when the OS appearance flips. Returns the unsubscribe. */
export function watchSystemTheme(onChange: (theme: Theme) => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  const listener = () => onChange(query.matches ? "dark" : "light");
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
