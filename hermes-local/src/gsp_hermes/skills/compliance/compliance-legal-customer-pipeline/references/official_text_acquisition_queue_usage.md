# Official Text Acquisition Queue Usage

Status: `LIVE_POINTER_ONLY_NO_CURRENT_QUEUE`

Historical official-text acquisition queues are not live query targets. This
reference intentionally contains no queue paths, counts, batch names, priority
labels, or generated-at timestamps.

For new official-text acquisition planning:

1. Read the live knowledge-base catalog JSON.
2. Resolve the active legal metadata classification table/view and any current
   executable-view artifacts from the catalog/manifest.
3. Build a fresh candidate queue from those current sources.
4. Keep the output candidate/not-live until separately approved and promoted.

Forbidden use: clause parsing, requirement atomization, checklist generation,
risk rating, legal advice, compliance conclusion, audit-pass claim, direct live
database writes, or confirmed factory baseline.
