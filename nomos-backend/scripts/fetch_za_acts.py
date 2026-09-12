#!/usr/bin/env python3
"""
Fetch the real South African Acts for the Week-2 corpus.

Sources (recorded in the manifest for provenance):
- Basic Conditions of Employment Act 75 of 1997 (as gazetted typeset edition):
  Department of Employment and Labour ecosystem mirror, gazette layout.
- Companies Act 71 of 2008 (as gazetted 2009-04-08):
  gov.za official Government Gazette PDF.

For each act the script:
1. downloads the PDF into data/gcs-layout/raw/za/acts/
2. extracts text with poppler pdftotext (poppler-utils)
3. records sha256 of both PDF and text
4. writes a manifest.json with provenance, dates, and checksums

Idempotent: skips download when the file already matches its recorded sha256.

The fabricated sample XMLs from the earlier week-2 attempt are moved to
_quarantine_fabricated/ (kept out of ingestion, not deleted).
"""

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data" / "gcs-layout" / "raw" / "za"
ACTS_DIR = BASE / "acts"
QUARANTINE = BASE / "_quarantine_fabricated"

ACTS = {
    "bcea": {
        "title": "Basic Conditions of Employment Act",
        "act_no": "Act 75 of 1997",
        "assent_date": "1997-12-02",
        "commencement_date": "1998-12-01",
        "pdf_name": "bcea_full.pdf",
        "text_name": "bcea_full.txt",
        "source_url": (
            "https://into-sa.com/wp-content/uploads/"
            "Basic_Conditions_of_Employment_Act__1997_.pdf"
        ),
        "source_note": (
            "Typeset gazette-layout edition of the Act as gazetted (1997). "
            "Mirror copy; official labour.gov.za amended-act PDF has "
            "corrupted font encoding. Text is a government edict (public domain)."
        ),
    },
    "companies_act": {
        "title": "Companies Act",
        "act_no": "Act 71 of 2008",
        "assent_date": "2009-04-08",
        "commencement_date": "2011-05-01",
        "pdf_name": "companies_act_full.pdf",
        "text_name": "companies_act_full.txt",
        "source_url": (
            "https://www.gov.za/sites/default/files/gcis_document/201409/321214210.pdf"
        ),
        "source_note": (
            "Official Government Gazette 32121 (9 April 2009) PDF from gov.za, "
            "as gazetted. Text is a government edict (public domain)."
        ),
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "nomos-corpus/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.rename(dest)


def extract_text(pdf_path: Path, text_path: Path) -> None:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(text_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr.strip()}")


def quarantine_fabricated() -> list[str]:
    """Move the fabricated week-2 sample XMLs out of the ingestion path."""
    moved = []
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    for name in ("bcea_full.xml", "companies_act_full.xml"):
        src = BASE / name
        if src.exists():
            dst = QUARANTINE / name
            shutil.move(str(src), str(dst))
            moved.append(name)
    readme = QUARANTINE / "README.md"
    if moved and not readme.exists():
        readme.write_text(
            "# Quarantined fabricated samples\n\n"
            "These XML files were created during the earlier week-2 attempt as\n"
            "hand-written stand-ins. They contain fabricated section text\n"
            "(e.g. an 'ammunition' definition inside the Companies Act) and must\n"
            "not be ingested. Real source PDFs + extracted text live in ../acts/.\n"
        )
    return moved


def main() -> int:
    ACTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "jurisdiction": "za",
        "fetched_at": datetime.now(UTC).isoformat(),
        "quarantined_fabricated": quarantine_fabricated(),
        "acts": {},
    }

    for key, meta in ACTS.items():
        pdf_path = ACTS_DIR / meta["pdf_name"]
        text_path = ACTS_DIR / meta["text_name"]

        if pdf_path.exists():
            actual = sha256_file(pdf_path)
            print(f"[{key}] PDF exists ({actual[:12]}...)")
        else:
            print(f"[{key}] downloading {meta['source_url']}")
            download(meta["source_url"], pdf_path)
            actual = sha256_file(pdf_path)
            print(f"[{key}] downloaded sha256={actual[:12]}...")

        if not text_path.exists():
            extract_text(pdf_path, text_path)
            print(f"[{key}] text extracted")

        text_chars = text_path.stat().st_size
        manifest["acts"][key] = {
            **meta,
            "pdf_sha256": actual,
            "text_sha256": sha256_file(text_path),
            "text_bytes": text_chars,
        }
        print(f"[{key}] ok: pdf={pdf_path.stat().st_size}B text={text_chars}B")

    out = ACTS_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
