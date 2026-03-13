## Summary

- changed domains:
- changed endpoint classes:
- contract audience:

## HTTP/API Review Checklist

- [ ] Endpoint ownership and route class are explicit.
- [ ] Handlers stay transport-only and receive only ready services/facades or standardized access deps.
- [ ] Request/response contracts use `Pydantic` schemas with explicit response models.
- [ ] Error mapping follows shared/domain API error policy.
- [ ] Launch mode and deployment profile exposure were reviewed, especially `ha_addon`.
- [ ] Idempotency, async trigger behavior, and conflict semantics were reviewed where relevant.
- [ ] `make openapi-check` was run for contract changes.
- [ ] `make api-matrix-export` was run when route exposure changed.
- [ ] Detailed checklist answers are captured in `docs/product/http-endpoint-review-checklist.md` when needed.

## Validation

- tests:
- docs/artifacts updated:
- migration notes:
