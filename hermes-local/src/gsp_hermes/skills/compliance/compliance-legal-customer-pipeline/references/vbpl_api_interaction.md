# VBPL API Interaction Reference

Status: accepted Hermes runtime guidance for candidate-only acquisition.

## Endpoint

- Base: `https://vbpl-bientap-gateway.moj.gov.vn/api`
- Full metadata/search endpoint: `POST /qtdc/public/doc/all`
- Detail endpoint: `GET /qtdc/public/doc/{doc_id}`

## Full Metadata Index Fetch

Use this when the user asks for a legal/regulatory index, asks whether the index
is complete, or asks whether the index was updated.

Request body:

```json
{
  "keyword": "",
  "pageSize": 5000,
  "pageNumber": 1
}
```

Important pagination behavior:

- `pageIndex` is ignored by the API.
- `pageNumber=0` and `pageNumber=1` both return the first page.
- `pageNumber=2` returns the next page.
- Always track IDs across pages. If row counts do not increase, stop and report
  a pagination failure instead of claiming completion.

As of 2026-05-25, the full A0/VBPL candidate metadata snapshot in the
compliance workspace is:

- Snapshot ID: `SN-VBPL-FULL-20260525-001`
- API total reported: `168018`
- Records fetched: `168018`
- Candidate DB: `/Users/HY-yin/.hermes/profiles/compliance/workspace/promotion_artifacts/legal_clause_acquisition/legal_index.candidate.sqlite`

## Parsing

VBPL responses can contain raw control characters. Clean the response before
JSON parsing:

```python
cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', raw_text)
data = json.loads(cleaned)
```

The search endpoint may include `docAbs`, which can be large. For an index
refresh, write metadata-only records and optionally store `docAbs` length/hash.
Do not claim official text archive unless the text is separately archived,
hashed, and reviewed.

## Coverage Boundary

VBPL is an official structured metadata baseline, not a complete Vietnam legal
universe. Even after full VBPL metadata pagination succeeds, keep A1/A2/A3 gap
routes open:

- A1 government portal and signed PDF sources.
- A2 official gazette/publication evidence.
- A3 ministry/authority sources and QCVN/technical annex sources.
- B-tier third-party datasets for discovery/cross-check only.

Forbidden claims:

- VBPL full metadata equals all Vietnam legal/regulatory documents.
- Candidate metadata index is a formal legal database.
- `docAbs` in a search response is an accepted official source archive.
- A keyword/sample fetch, such as 94 rows, is a complete legal/regulatory index.
