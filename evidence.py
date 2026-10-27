"""Date- and ticker-scoped lexical retrieval with explicit source metadata."""
import json
import re
from datetime import date
from pathlib import Path


def load_evidence(folder, as_of):
    folder = Path(folder).resolve()
    cutoff = date.fromisoformat(as_of)
    manifest = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("Report index must be a list")
    records = []
    source_ids = set()
    for entry in manifest:
        if not isinstance(entry, dict):
            raise ValueError("Each report index entry must be an object")
        published = date.fromisoformat(entry["published_at"])
        if published > cutoff:
            continue
        path = (folder / entry["filename"]).resolve()
        if not path.is_relative_to(folder):
            raise ValueError("Report filename must stay inside the report directory")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Report exceeds the 10 MiB limit")
        symbol = str(entry["ticker"]).strip().upper()
        if not symbol:
            raise ValueError("Report ticker cannot be empty")
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            if len(reader.pages) > 300:
                raise ValueError("PDF exceeds 300 pages")
            pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
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
    if not 1 <= limit <= 10:
        raise ValueError("Retrieval limit must be between 1 and 10")
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
