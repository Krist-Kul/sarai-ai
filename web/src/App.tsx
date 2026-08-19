import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

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
    <div className="flex rounded-full border border-line bg-surface p-0.5 text-xs font-semibold cursor-pointer">
      {(["th", "en"] as const).map((code) => (
        <button
          key={code}
          onClick={() => setLang(code)}
          className={`rounded-full px-2.5 py-1 cursor-pointer ${
            lang === code ? "bg-ink-900 text-surface" : "text-ink-600 hover:text-ink-900"
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
  return (
    <div className="border-b border-warn-line bg-warn-50 px-4 py-2.5 text-sm text-warn-700 sm:px-6">
      <div className="mx-auto flex max-w-6xl items-center gap-2.5">
        <span className="size-1.5 shrink-0 rounded-full bg-warn-500" aria-hidden />
        {t("workerDown")}
      </div>
    </div>
  );
}

function Header() {
  const { t } = useI18n();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-full px-3.5 py-1.5 text-sm ${
      isActive ? "bg-sand font-semibold text-ink-900" : "text-ink-600 hover:text-ink-900"
    }`;
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-[9px] bg-brand-600 text-sm font-bold text-white">
            S
          </span>
          <span className="text-[17px] font-bold tracking-tight">{t("appName")}</span>
          <span className="hidden text-xs text-ink-400 md:inline">{t("tagline")}</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1.5">
          <NavLink to="/" end className={linkClass}>
            {t("meetings")}
          </NavLink>
          <LanguageToggle />
          <Link
            to="/new"
            className="ml-1 rounded-full bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-600/90"
          >
            <span aria-hidden>＋ </span>
            {t("newMeeting")}
          </Link>
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
        <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-9">
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
