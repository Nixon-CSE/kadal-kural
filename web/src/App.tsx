import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { DeskProvider } from "@/app/DeskProvider";
import { Layout } from "@/app/Layout";
import DeskPage from "@/pages/DeskPage";
import HomePage from "@/pages/HomePage";

const LedgerPage = lazy(() => import("@/pages/LedgerPage"));
const BuyersPage = lazy(() => import("@/pages/BuyersPage"));
const InsightsPage = lazy(() => import("@/pages/InsightsPage"));
const PhonePage = lazy(() => import("@/pages/PhonePage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

const page = (el: React.ReactNode) => <Suspense fallback={<div className="h-[60vh] animate-pulse rounded-3xl bg-white/50" />}>{el}</Suspense>;

export default function App() {
  return (
    <BrowserRouter>
      <DeskProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="desk" element={<DeskPage />} />
            <Route path="ledger" element={page(<LedgerPage />)} />
            <Route path="buyers" element={page(<BuyersPage />)} />
            <Route path="insights" element={page(<InsightsPage />)} />
            <Route path="phone" element={page(<PhonePage />)} />
            <Route path="*" element={page(<NotFoundPage />)} />
          </Route>
        </Routes>
      </DeskProvider>
    </BrowserRouter>
  );
}
