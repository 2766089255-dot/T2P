# Contributing

## Record the problem

Open an issue for a reproducible bug or a scoped improvement. Include the current
behavior, expected behavior, reproduction steps, and relevant environment details.
For an AI-output problem, use an anonymized example and describe how the result
was checked.

## Make and review a change

1. Create a branch for one coherent change.
2. Add or update tests when behavior changes.
3. Open a pull request explaining the problem, resulting behavior, validation,
   and any remaining limitations. Link the issue with `Closes #<number>` when the
   change fully resolves it.
4. Inspect the diff and wait for CI before merging.

Do not include API keys, `.env` files, student submissions, generated user records,
model caches, or local audit reports in a pull request.

## Run the same checks as CI

### Backend

Create and activate a Python 3.12 or 3.13 virtual environment, then install the
lightweight test dependencies from the repository root:

```bash
python -m pip install -r requirements-ci.txt
python -m pip check
python -m unittest discover -s tests -v
python audit_dataset.py --dataset data/golden_dataset_v3.json --output-dir reports
```

Run these checks without a configured DeepSeek API key. Set
`ENABLE_SEMANTIC_DEDUP=false` and `MPLBACKEND=Agg` for a lightweight, headless
test environment. The existing suite uses fake AI/OCR responses where needed.
It does not verify live-provider responses, OCR accuracy on real handwriting,
or Transformer embedding quality. Use `requirements.txt` for the full application.

The audit command checks that an offline report can be generated. Its findings
are review items, not a mathematical-correctness certificate or a zero-error
quality gate. Inspect `reports/dataset_audit.md` and the corresponding JSON.

### Frontend

With Node.js 24 installed:

```bash
cd t2p-web
npm ci --no-audit --no-fund
npm run lint
npm run typecheck
npm run build
```

`typecheck` generates Next.js route declarations before checking TypeScript.
No backend server or provider key is required for these frontend checks.

## Release a verified snapshot

After a coherent milestone is merged and the default-branch checks pass, create
a tag and a release. Describe the actual changes, link validation evidence, and
state limitations. Repository release versions describe portfolio snapshots;
they do not imply a change to the API schema or frontend package version.
