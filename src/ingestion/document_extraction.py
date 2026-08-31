"""Document Extraction agent (docs/architecture.md §3.1): turn an invoice
PDF into structured fields via a vision-capable model. This is a READ, same
grounding discipline as extract_claim in the orchestration graph — the
extracted fields get compared against Postgres, never trusted standalone.

No external binary dependency for PDF rendering (no poppler/ImageMagick):
PyMuPDF rasterizes the page in-process.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymupdf
from pydantic import BaseModel, Field

from src.orchestration.llm import get_llm


class ExtractedInvoice(BaseModel):
    invoice_number: str = Field(description="the invoice/document number as printed")
    total_amount: float = Field(description="the total payable amount, as a plain decimal number")
    currency: str = Field(description="ISO 4217 currency code, e.g. EUR")
    seller_name: str = Field(description="the invoicing party's legal name")
    buyer_name: str = Field(description="the recipient party's legal name")
    due_date: str = Field(description="payment due date in YYYY-MM-DD format")


def render_pdf_page_to_png_base64(pdf_path: str, page_number: int = 0, dpi: int = 150) -> str:
    doc = pymupdf.open(pdf_path)
    page = doc[page_number]
    pix = page.get_pixmap(dpi=dpi)
    png_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(png_bytes).decode("ascii")


def extract_invoice(pdf_path: str) -> ExtractedInvoice:
    image_b64 = render_pdf_page_to_png_base64(pdf_path)

    llm = get_llm("strong").with_structured_output(ExtractedInvoice)
    result: ExtractedInvoice = llm.invoke([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract the structured fields from this invoice."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }
    ])
    return result


def demo() -> None:
    pdf_path = str(Path(__file__).resolve().parents[2] / "data" / "seed" / "invoices" / "INV-1002.pdf")
    result = extract_invoice(pdf_path)
    print(f"extracted: {result}")

    # Ground truth from what was actually sent to the Scribo API (see
    # data/seed/invoices/README.md): line amount EUR 9800.00 at 19% VAT, so
    # the invoice TOTAL (what should appear on the document) is
    # 9800 * 1.19 = 11662.00. due_date was never set in the API payload, so
    # it's whatever Scribo defaulted to — not asserted against a fixed value.
    assert result.invoice_number, "invoice_number should not be empty"
    assert abs(result.total_amount - 11662.00) < 1.0, f"expected ~11662.00 (9800 net + 19% VAT), got {result.total_amount}"
    assert result.currency == "EUR", result.currency
    assert "Kessler" in result.seller_name, result.seller_name
    assert "Nordwind" in result.buyer_name, result.buyer_name
    assert result.due_date, "due_date should not be empty"

    print("document_extraction.demo(): extracted fields match known ground truth")


if __name__ == "__main__":
    demo()
