import { useDeskContext } from "@/app/desk-context";
import { Ledger } from "@/components/desk/Ledger";

import { PageHeading } from "./PageHeading";

export default function LedgerPage() {
  const desk = useDeskContext();
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeading title="Ledger" lead="Every decision the desk made, newest first. Undo never deletes: it adds a reversing entry and strikes the original through. Select a row for the full story and a payment QR." />
      <Ledger events={desk.desk?.events ?? []} buyers={desk.desk?.buyers ?? []} gate={desk.desk?.confidence_threshold ?? 0.82} newIds={desk.newIds} full />
    </div>
  );
}
