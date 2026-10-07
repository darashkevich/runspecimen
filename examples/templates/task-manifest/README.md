# Example task manifest (ADR-005)

```json
{
  "schema_kind": "task_manifest",
  "schema_version": 1,
  "id": "example-checks",
  "description": "Provider-collected checks; never embed a passed field",
  "requirements": [
    {
      "id": "unit-smoke",
      "description": "Stdlib unittest smoke",
      "check": {
        "provider": "unittest",
        "id": "smoke",
        "config": { "start_dir": "tests", "pattern": "test_*.py" }
      },
      "inputs": [],
      "source_scope": ["src"],
      "required_evidence": ["unittest_stream_sha256"],
      "expected": {},
      "rationale": "Configured checks passing is not universal correctness"
    }
  ]
}
```

Bind `artifact_digest` with `runspecimen requirements validate` after editing
(or let tooling compute it). See `docs/ADR-005-evidence-expansion.md`.
