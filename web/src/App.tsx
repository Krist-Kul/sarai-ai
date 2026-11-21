import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ButtonLink, Mark, Notice } from "./components/ui";
import { api } from "./lib/api";
import { LangContext, loadLang, saveLang, useI18n, type Lang } from "./lib/i18n";
import {
  applyTheme,
  loadThemePref,
  saveThemePref,
  systemTheme,
  watchSystemTheme,
  type Theme,
  type ThemePref,
} from "./lib/theme";
import { MeetingsPage } from "./pages/MeetingsPage";
import { NewMeetingPage } from "./pages/NewMeetingPage";
import { MeetingPage } from "./pages/MeetingPage";
import { ReviewPage } from "./pages/ReviewPage";
import { MinutesPage } from "./pages/MinutesPage";

function LanguageToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="flex rounded-full border border-line bg-surface-raised p-[3px]">
      {(["th", "en"] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`cursor-pointer rounded-full px-3 py-1 text-small-strong ${
            lang === code ? "bg-ink text-on-ink" : "text-ink-muted hover:text-ink"
          }`}
        >
          {code === "th" ? "ไทย" : "EN"}
        </button>
      ))}
    </div>
  );
}

const THEME_ICONS: Record<ThemePref, ReactNode> = {
  system: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </>
  ),
  light: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </>
  ),
  dark: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
};

const THEME_LABELS = { system: "themeSystem", light: "themeLight", dark: "themeDark" } as const;

function ThemeToggle() {
  const { t } = useI18n();
  const [pref, setPref] = useState<ThemePref>(() => loadThemePref());
  const [system, setSystem] = useState<Theme>(() => systemTheme());

  // Track the OS appearance always; it only shows while the pref is "system".
  useEffect(() => watchSystemTheme(setSystem), []);
  useEffect(() => applyTheme(pref === "system" ? system : pref), [pref, system]);

  return (
    <div
      role="radiogroup"
      aria-label={t("theme")}
      className="flex rounded-full border border-line bg-surface-raised p-[3px]"
    >
      {(["system", "light", "dark"] as const).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={pref === option}
          aria-label={t(THEME_LABELS[option])}
          title={t(THEME_LABELS[option])}
          onClick={() => {
            saveThemePref(option);
            setPref(option);
          }}
          className={`grid size-[28px] cursor-pointer place-items-center rounded-full ${
            pref === option ? "bg-ink text-on-ink" : "text-ink-muted hover:text-ink"
          }`}
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {THEME_ICONS[option]}
          </svg>
        </button>
      ))}
    </div>
  );
}

function WorkerBanner() {
  const { t } = useI18n();
  // Health is cheap and tells the user why nothing is moving.
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
  });
  if (!data || data.worker_alive) return null;
  return <Notice tone="live">{t("workerDown")}</Notice>;
}

function Header() {
  const { t } = useI18n();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    // Hidden on phones: the logo already goes to the list, and the row has no room.
    `whitespace-nowrap rounded-full px-3.5 py-1.5 text-label max-sm:hidden ${
      isActive ? "bg-surface-raised text-ink" : "text-ink-muted hover:text-ink"
    }`;
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/80 backdrop-blur-[16px]">
      <div className="mx-auto flex min-h-16 max-w-[1152px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-6">
        <Link to="/" className="flex items-center" aria-label={t("appName")}>
          <Mark />
        </Link>
        <span className="hidden text-small text-ink-subtle md:inline">{t("tagline")}</span>
        <nav className="ml-auto flex items-center gap-1.5">
          <NavLink to="/" end className={linkClass}>
            {t("meetings")}
          </NavLink>
          <LanguageToggle />
          <ThemeToggle />
          <ButtonLink to="/new" icon="upload" className="ml-1 max-sm:h-8 max-sm:px-4">
            {t("newMeeting")}
          </ButtonLink>
        </nav>
      </div>
    </header>
  );
}

export default function App() {
  const [lang, setLangState] = useState<Lang>(() => loadLang());

  const setLang = useCallback((next: Lang) => {
    saveLang(next);
    setLangState(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const ctx = useMemo(() => ({ lang, setLang }), [lang, setLang]);

  return (
    <LangContext.Provider value={ctx}>
      <div className="min-h-screen">
        <WorkerBanner />
        <Header />
        <main className="mx-auto max-w-[1152px] px-4 pt-8 pb-16 sm:px-6 sm:pt-10 sm:pb-[72px]">
          <Routes>
            <Route path="/" element={<MeetingsPage />} />
            <Route path="/new" element={<NewMeetingPage />} />
            <Route path="/meetings/:id" element={<MeetingPage />} />
            <Route path="/meetings/:id/review" element={<ReviewPage />} />
            <Route path="/meetings/:id/minutes" element={<MinutesPage />} />
          </Routes>
        </main>
      </div>
    </LangContext.Provider>
  );
}
