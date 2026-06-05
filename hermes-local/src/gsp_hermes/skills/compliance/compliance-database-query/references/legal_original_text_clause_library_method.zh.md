# Legal Original Text Clause Library Method

Status: `LIVE_POINTER_ONLY`

This reference intentionally contains no live counts, no source-gap status, and
no hardcoded metadata classification table/view. For each lookup:

1. Read the live knowledge-base catalog JSON.
2. Resolve the current legal clause entry, manifest path, live sqlite path, and
   query view from the catalog/manifest.
3. Query the sqlite database directly and cite the table/view counted.
4. If skill prose or old references conflict with catalog/manifest/sqlite,
   catalog/manifest/sqlite wins.

Allowed use: original legal text lookup, article/clause text lookup, source
traceability, full-text search, and pre-requirement clause review.

Blocked use: requirement atoms, checklist generation, legal advice, compliance
conclusion, risk rating, audit-pass claim, and confirmed factory baseline.
