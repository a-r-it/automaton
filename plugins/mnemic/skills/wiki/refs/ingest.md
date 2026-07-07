# ingest

Copy a file into `sources/` for the next compile to pick up.

```bash
wiki-ingest <path>
```

**Args:**
- `<path>` — required, source file to ingest.

**Notes:**
- Skips if a file with the same basename already exists in `sources/`.
  Run `mnemic:wiki compile` (or `compile --all`) to reprocess.
