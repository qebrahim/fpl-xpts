import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'fplxpts-theme';
const THEME_COLORS: Record<Theme, string> = { light: '#f7f7f8', dark: '#111214' };
const DARK_QUERY = '(prefers-color-scheme: dark)';

function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

/** Follows the system until the user picks a theme, then persists the explicit choice. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [explicit, setExplicit] = useState<Theme | null>(storedTheme);
  const [system, setSystem] = useState<Theme>(systemTheme);

  useEffect(() => {
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = (e: MediaQueryListEvent) => setSystem(e.matches ? 'dark' : 'light');
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const theme = explicit ?? system;

  useEffect(() => {
    if (explicit === null) return;
    document.documentElement.setAttribute('data-theme', explicit);
    document
      .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
      .forEach((meta) => meta.setAttribute('content', THEME_COLORS[explicit]));
    try {
      localStorage.setItem(STORAGE_KEY, explicit);
    } catch {
      /* storage unavailable: the choice lasts for this page view only */
    }
  }, [explicit]);

  const toggle = useCallback(() => setExplicit(theme === 'dark' ? 'light' : 'dark'), [theme]);
  return { theme, toggle };
}
