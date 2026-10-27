"""Date- and ticker-scoped lexical retrieval with explicit source metadata."""
import json
import re
from pathlib import Path

from inputs import iso_date, ticker as normalize_ticker


def load_evidence(folder, as_of):
    folder = Path(folder).resolve()
    cutoff = iso_date(as_of, "as_of")
    manifest = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("Report index must be a list")
    records = []
    source_ids = set()
    seen_files = set()
    for entry in manifest:
        if not isinstance(entry, dict):
            raise ValueError("Each report index entry must be an object")
        published = iso_date(entry["published_at"], "published_at")
        if published > cutoff:
            continue
        filename = entry["filename"]
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Report filename must be a nonempty string")
        symbol = normalize_ticker(entry["ticker"])
        path = (folder / filename).resolve()
        if not path.is_relative_to(folder):
            raise ValueError("Report filename must stay inside the report directory")
        if path in seen_files:
            raise ValueError("Duplicate report file in index")
        seen_files.add(path)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Report exceeds the 10 MiB limit")
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
            try:
                reader = PdfReader(path)
                if reader.is_encrypted:
                    raise ValueError("Encrypted PDF reports are not supported")
                if len(reader.pages) > 300:
                    raise ValueError("PDF exceeds 300 pages")
                pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
            except PdfReadError as exc:
                raise ValueError(f"Invalid PDF report {filename}: {exc}") from exc
        elif path.suffix.lower() in {".txt", ".md"}:
            pages = [(None, path.read_text(encoding="utf-8"))]
        else:
            raise ValueError("Reports support .pdf, .txt or .md")
        if sum(len(text) for _, text in pages) > 2_000_000:
            raise ValueError("Report has too much extracted text")
        for page, text in pages:
            for index, start in enumerate(range(0, len(text), 1200)):
                content = text[start:start + 1400].strip()
                if not content:
                    continue
                source_id = f"{entry['filename']}:{page or 0}:{index}"
                if source_id in source_ids:
                    raise ValueError("Duplicate report source ID")
                source_ids.add(source_id)
                records.append({"source_id": source_id, "ticker": symbol,
                                "filename": entry["filename"], "page": page,
                                "published_at": published.isoformat(), "text": content})
    return records


def retrieve(records, ticker, query="business growth risk debt revenue", limit=3):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("Retrieval limit must be between 1 and 10")
    ticker = normalize_ticker(ticker)
    if not isinstance(query, str):
        raise ValueError("Retrieval query must be a string")
    words = set(re.findall(r"\w{3,}", query.casefold()))
    candidates = []
    for record in records:
        if record["ticker"] not in {ticker.upper(), "*"}:
            continue
        tokens = set(re.findall(r"\w{3,}", record["text"].casefold()))
        score = len(words & tokens)
        if score:
            candidates.append((score, record))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]["source_id"]))
    return [record for _, record in candidates[:limit]]
