# ZA Legal Corpus GCS Snapshot

This directory contains the Google Cloud Storage snapshot of the South African legal corpus.
Using this snapshot prevents the system from making live API calls to Laws.Africa, thus avoiding quota consumption.

## Directory Structure

```
raw/           - Raw legal documents as obtained from Laws.Africa (XML format)
parsed/        - Parsed sections and heading trees (JSON format)
versions/      - Versioned snapshots of the corpus
manifests/     - Manifest files listing available sections and metadata
```

## Files in this snapshot

### Raw Data (`raw/za/`)
- `bcea_full.xml` - Basic Conditions of Employment Act 75 of 1997
- `companies_act_full.xml` - Companies Act 71 of 2008

### Manifest (`manifests/za_manifest.json`)
- Lists all available sections in the corpus
- Includes a "smoke section" (`za_smoke_section_999`) for testing the manifest-check script
- Provides metadata for each section (act name, chapter, etc.)

## Usage in the NOMOS System

The ingestion pipeline is configured to:
1. Read raw data from `gs://nomos-legal-corpus/raw/za/` instead of calling Laws.Africa API
2. Parse the XML documents into structured sections
3. Store parsed results in `gs://nomos-legal-corpus/parsed/za/`
4. Generate manifests in `gs://nomos-legal-corpus/manifests/za_manifest.json`
5. Use the manifest-check script to validate completeness before processing

## Benefits of this approach

1. **Quota Prevention**: No live API calls to Laws.Africa during normal operation
2. **Consistency**: Fixed snapshot ensures reproducible results
3. **Performance**: Faster access to pre-stored GCS data vs. network API calls
4. **Reliability**: Independent of Laws.Africa API availability or rate limits
5. **Versioning**: Ability to maintain multiple corpus versions for A/B testing

## Testing the Manifest Check

To verify that the manifest-check script works correctly with this snapshot:

```bash
python3 scripts/manifest-check.py data/gcs-layout/manifests/za_manifest.json data/gcs-layout/parsed/za/
```

Note: The parsed directory would be populated after running the ingestion pipeline on the raw data.
