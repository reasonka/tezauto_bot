import io
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pdfplumber


CODE_REGEX = re.compile(r"\b([PBCU][0-3][0-9A-F]{3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedReport:
    filename: str
    text: str
    codes: List[str]
    notes: List[str]


def _decode_text_bytes(data: bytes) -> str:
    # Best-effort decode without guessing too hard.
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_from_pdf(data: bytes) -> Tuple[str, List[str]]:
    text_parts: List[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
    text = "\n\n".join(text_parts).strip()
    codes = _extract_codes(text)
    return text, codes


def _extract_codes(text: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in CODE_REGEX.finditer(text):
        code = m.group(1).upper()
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def extract_text_and_codes(
    filename: str,
    content_type: Optional[str],
    data: bytes,
) -> ExtractedReport:
    """
    Extract text + OBD2-style codes from common report formats.
    Supported:
      - PDF
      - text/plain
      - CSV (treated as text)
    """
    notes: List[str] = []
    lower = filename.lower()

    if lower.endswith(".pdf") or (content_type == "application/pdf"):
        text, codes = _extract_from_pdf(data)
        if not text:
            notes.append("PDF text extraction returned empty text (may be scanned images).")
        return ExtractedReport(filename=filename, text=text, codes=codes, notes=notes)

    # Treat anything else as text-ish (txt, csv, log, etc.)
    text = _decode_text_bytes(data)
    if lower.endswith(".csv"):
        notes.append("CSV parsed as plain text (no structured column parsing).")
    codes = _extract_codes(text)
    return ExtractedReport(filename=filename, text=text, codes=codes, notes=notes)

