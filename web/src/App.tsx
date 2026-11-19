import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ButtonLink, Mark, Notice } from "./components/ui";
import { api } from "./lib/api";
import { LangContext, loadLang, saveLang, useI18n, type Lang } from "./lib/i18n";
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
