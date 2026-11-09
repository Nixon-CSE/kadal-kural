import { BrowserRouter, Route, Routes } from "react-router";

import { DeskProvider } from "@/app/DeskProvider";
import { Layout } from "@/app/Layout";
import BuyersPage from "@/pages/BuyersPage";
import DeskPage from "@/pages/DeskPage";
import HomePage from "@/pages/HomePage";
import InsightsPage from "@/pages/InsightsPage";
import LedgerPage from "@/pages/LedgerPage";
import NotFoundPage from "@/pages/NotFoundPage";
import PhonePage from "@/pages/PhonePage";
import PlayPage from "@/pages/PlayPage";

// Pages are small and imported directly: a lazy page suspends on every first visit and React holds
// the fallback for 300 ms. The heavy parts (three.js scenes) stay lazy inside the pages.
export default function App() {
  return (
    <BrowserRouter>
      <DeskProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="play" element={<PlayPage />} />
            <Route path="desk" element={<DeskPage />} />
            <Route path="ledger" element={<LedgerPage />} />
            <Route path="buyers" element={<BuyersPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="phone" element={<PhonePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </DeskProvider>
    </BrowserRouter>
  );
}
