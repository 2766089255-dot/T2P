# Changelog

## 0.1.0 - 2026-11-10

### Added

- GitHub Actions checks for the existing backend suite on Python 3.12 and 3.13.
- An offline dataset-audit execution check and a lightweight test dependency set.
- Frontend lint, route-aware TypeScript checks, and production builds on Node.js 24.
- Contribution, pull-request, and verified-snapshot release guidance.

### Scope

- Backend checks cover the existing offline tests; live LLM/OCR services and
  Transformer embedding quality are outside this CI suite.
- Dataset-audit findings are reported for review rather than treated as proof of
  mathematical correctness.
