# skill: gemini-classification

## When to use
Use when tasks affect Gemini-based document classification, entity extraction, PII detection, or prompt normalization.

## Inputs
- `FileIndex` or extracted text.
- `gemini_api_key` availability.
- Target classification schema.

## Procedure (step-by-step, deterministic)
1. Check whether Gemini is configured in `backend/app/config.py`.
2. If no key exists, return the stub metadata path used by `backend/app/services/gemini_service.py`.
3. If text is available, classify from extracted text before falling back to file bytes.
4. Normalize category, keywords, risk level, dates, and confidence to the schema.
5. Keep outputs compatible with `DocumentMetadata`.

## Constraints (hard rules)
- Do not fabricate categories outside `DocumentCategory`.
- Do not emit invalid dates or confidence values outside 0 to 1.
- Do not leak unsupported free-form text outside the JSON contract.

## Output (structured)
- `DocumentMetadata` candidate.
- Category.
- Entities.
- Relations.
- Semantic summary.
- PII status.

## Evidence Sources (files, modules, data)
- `backend/app/services/gemini_service.py`
- `backend/app/models/schemas.py`
- `backend/app/config.py`
- `tests/test_gemini_service.py`

## Anti-patterns
- Returning an object that does not validate as `DocumentMetadata`.
- Ignoring the stub path when Gemini is unavailable.
- Emitting uncontrolled prose instead of the JSON schema.
