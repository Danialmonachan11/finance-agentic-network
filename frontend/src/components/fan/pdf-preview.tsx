import { useEffect } from "react";
import { Button } from "@/components/fan/ui";
import { documentFor, money, shortDate, dateTime, type InvoiceDocument } from "@/lib/fan-data";

/**
 * Preview panel for invoices that really have a generated PDF on disk.
 * Rows without a document never open this — they say so instead.
 */
export function PdfPreviewModal({
  doc,
  onClose,
}: {
  doc: InvoiceDocument;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const total = doc.lines.reduce((s, l) => s + l.qty * l.unit_price, 0);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#16171c]/70 px-4 py-8 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label={`Document preview for ${doc.invoice_number}`}
      onClick={onClose}
    >
      <div
        className="surface w-full max-w-3xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <p className="label-mono">Document preview</p>
            <h2 className="num mt-1 text-lg font-semibold">{doc.filename}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              A real generated PDF on disk — {doc.pages} page{doc.pages > 1 ? "s" : ""},{" "}
              {doc.size_kb.toFixed(1)} KB, written {dateTime(doc.generated_at)}. What you see below
              is a rendering of its contents, not a scan.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm">Download</Button>
            <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close preview">
              Close
            </Button>
          </div>
        </header>

        <div className="max-h-[70vh] overflow-y-auto bg-secondary/50 p-6">
          <article className="mx-auto max-w-xl border border-border bg-card p-8 shadow-sm">
            <div className="flex items-start justify-between border-b border-border pb-5">
              <div>
                <p className="label-mono">Invoice</p>
                <p className="num mt-1 text-xl font-semibold">{doc.invoice_number}</p>
              </div>
              <div className="text-right text-xs">
                <p className="label-mono">Due</p>
                <p className="num mt-1 font-semibold">{shortDate(doc.due_date)}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-6 border-b border-border py-5 text-xs">
              <div>
                <p className="label-mono mb-1">From</p>
                <p className="font-medium">{doc.issued_by}</p>
              </div>
              <div>
                <p className="label-mono mb-1">To</p>
                <p className="font-medium">{doc.issued_to}</p>
              </div>
            </div>

            <table className="w-full border-collapse py-4 text-xs">
              <thead>
                <tr>
                  <th className="label-mono border-b border-border py-2 text-left font-medium">
                    Description
                  </th>
                  <th className="label-mono border-b border-border py-2 text-right font-medium">
                    Qty
                  </th>
                  <th className="label-mono border-b border-border py-2 text-right font-medium">
                    Unit
                  </th>
                  <th className="label-mono border-b border-border py-2 text-right font-medium">
                    Line
                  </th>
                </tr>
              </thead>
              <tbody>
                {doc.lines.map((l) => (
                  <tr key={l.description}>
                    <td className="border-b border-border py-2 pr-3">{l.description}</td>
                    <td className="num border-b border-border py-2 text-right">{l.qty}</td>
                    <td className="num border-b border-border py-2 text-right">
                      {money(l.unit_price)}
                    </td>
                    <td className="num border-b border-border py-2 text-right font-semibold">
                      {money(l.qty * l.unit_price)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3} className="label-mono py-3 text-right">
                    Total
                  </td>
                  <td className="num py-3 text-right text-sm font-semibold">{money(total)}</td>
                </tr>
              </tfoot>
            </table>

            <p className="mt-4 border-t border-border pt-4 text-2xs leading-relaxed text-muted-foreground">
              {doc.notes}
            </p>
          </article>
        </div>
      </div>
    </div>
  );
}

/**
 * Table cell for the document column. Honest about seeded rows:
 * no icon, no link, no implied file.
 */
export function DocumentCell({
  invoiceNumber,
  hasPdf,
  onOpen,
}: {
  invoiceNumber: string;
  hasPdf: boolean;
  onOpen: (doc: InvoiceDocument) => void;
}) {
  const doc = hasPdf ? documentFor(invoiceNumber) : undefined;

  if (!doc) {
    return (
      <span className="text-xs text-muted-foreground">No document — seeded row</span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(doc)}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-primary underline underline-offset-4 transition-colors hover:text-primary-hover focus:outline-none focus-visible:text-primary-hover"
    >
      <span aria-hidden className="num text-[9px] rounded-sm border border-primary px-1 py-px">
        PDF
      </span>
      Preview document
    </button>
  );
}
