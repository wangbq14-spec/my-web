export const THEME_STORAGE_KEY = 'omnixa-theme'

export function readTheme() {
  if (typeof document === 'undefined') return 'light'
  const activeTheme = document.documentElement.dataset.theme
  if (activeTheme === 'dark' || activeTheme === 'light') return activeTheme

  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function applyTheme(nextTheme) {
  if (typeof document === 'undefined') return 'light'
  document.documentElement.dataset.theme = nextTheme
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme)
  } catch {
    // Theme preference remains available for the current session.
  }
  return nextTheme
}
