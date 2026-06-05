# Service And Reimbursement Flow

## Service Flow

1. A request enters the service router with a profile name and action.
2. The profile registry loads accepted policy from `hermes-local/config/profiles`.
3. The router blocks admin actions unless the accepted profile is `admin` and admin-capable.
4. Business actions are dispatched to the profile-specific boundary module.
5. Runtime state paths are resolved under `.hermes/profiles/<profile>`.

## Reimbursement Flow

1. `reimbursement` receives a reimbursement intake request.
2. The reimbursement profile asks the OCR policy selector for `reimbursement_ocr_extraction`.
3. Extracted fields are validated against reimbursement requirements.
4. Evidence and draft outputs are written to the reimbursement runtime profile tree.
5. No legacy backup code is executed by this flow.

## OCR Policy Split

- `shared_ocr`: common OCR engine constraints and redaction rules.
- `compliance_ocr_extraction`: clauses, source, page, version, and evidence trace.
- `reimbursement_ocr_extraction`: invoice number, amount, vendor, date, tax id, currency, and expense category.
