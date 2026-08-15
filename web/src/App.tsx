import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "./lib/api";
import { LangContext, loadLang, saveLang, useI18n, type Lang } from "./lib/i18n";
import { MeetingsPage } from "./pages/MeetingsPage";
import { NewMeetingPage } from "./pages/NewMeetingPage";
import { MeetingPage } from "./pages/MeetingPage";

function LanguageToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-medium">
      {(["th", "en"] as const).map((code) => (
        <button
          key={code}
          onClick={() => setLang(code)}
          className={`rounded-md px-2.5 py-1 ${
            lang === code ? "bg-brand-600 text-white" : "text-ink-600 hover:bg-slate-100"
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
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
      {t("workerDown")}
    </div>
  );
}

function Header() {
  const { t } = useI18n();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium ${
      isActive ? "bg-slate-100 text-ink-900" : "text-ink-600 hover:bg-slate-100"
    }`;
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
        <Link to="/" className="flex items-baseline gap-2">
          <span className="text-lg font-semibold tracking-tight">{t("appName")}</span>
          <span className="hidden text-xs text-ink-400 sm:inline">{t("tagline")}</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1">
          <NavLink to="/" end className={linkClass}>
            {t("meetings")}
          </NavLink>
          <NavLink to="/new" className={linkClass}>
            {t("newMeeting")}
          </NavLink>
          <LanguageToggle />
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
        <main className="mx-auto max-w-5xl px-4 py-8">
          <Routes>
            <Route path="/" element={<MeetingsPage />} />
            <Route path="/new" element={<NewMeetingPage />} />
            <Route path="/meetings/:id" element={<MeetingPage />} />
          </Routes>
        </main>
      </div>
    </LangContext.Provider>
  );
}
