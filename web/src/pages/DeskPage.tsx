import { useOutletContext } from "react-router";

import { useDeskContext } from "@/app/desk-context";
import { CreditGauges } from "@/components/desk/CreditGauges";
import { Ledger } from "@/components/desk/Ledger";
import { LiveTurn } from "@/components/desk/LiveTurn";
import { Pipeline } from "@/components/desk/Pipeline";
import { Stats } from "@/components/desk/Stats";

import type { LayoutOutlet } from "./layout-outlet";

export default function DeskPage() {
  const desk = useDeskContext();
  const { inputRef } = useOutletContext<LayoutOutlet>();
  const gate = desk.desk?.confidence_threshold ?? 0.82;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <LiveTurn desk={desk} inputRef={inputRef} />
        <aside className="grid content-start gap-5">
          <CreditGauges buyers={desk.desk?.buyers ?? []} touched={desk.touched} />
          <Pipeline stage={desk.stage} gate={gate} />
        </aside>
      </div>
      <Stats events={desk.desk?.events ?? []} history={desk.history} />
      <Ledger events={desk.desk?.events ?? []} gate={gate} newIds={desk.newIds} limit={8} />
    </div>
  );
}
