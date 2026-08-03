# Installed Postly API endpoint inventory

Source evidence is the exact deployed `v2.22.1` tree at commit `c90b6c625bc0ec470d6dcdb57c63608aaa9b7b74`, principally `apps/backend/src/public-api/routes/v1/public.integrations.controller.ts` and `services/auth/public.auth.middleware.ts`.

Base URL for this deployment: `https://social.codestra.co/api/public/v1`. The installed `NEXT_PUBLIC_BACKEND_URL` routing requires the `/api` prefix: an unauthenticated probe to `/api/public/v1/integrations` returned the expected API 401, while `/public/v1/integrations` redirected to `/auth`. Authentication is the raw organization API key in `Authorization`; missing and invalid keys return JSON `{ "msg": ... }` with 401. API keys are organization-scoped and resolved server-side. OAuth tokens beginning `pos_` are also accepted, but are not selected for this integration.

| Method/path | Installed behavior | Adapter use |
|---|---|---|
| `GET /integrations?group=` | Org-filtered integration metadata | list integrations |
| `GET /integration-settings/{id}` | provider rules, max length, schema and tools; 404 if not in org | settings |
| `GET /find-slot/{integrationId}` | returns `{date}` | locate slot |
| `POST /upload` | multipart field `file`; validated limits | upload media |
| `POST /upload-from-url` | public HTTPS URL, SSRF guard, MIME sniff and size checks | optional staged media |
| `GET /posts?startDate=&endDate=&customer=` | ISO date range; org-filtered | list/reconcile |
| `POST /posts` | maps, validates, then creates draft/scheduled group | schedule approved post only |
| `DELETE /posts/{id}` | resolves org-owned post then deletes its group | cancel |
| `DELETE /posts/group/{group}` | deletes org-owned group | cancel group |
| `GET /posts/{id}/missing` | missing provider content | reconciliation |
| `PUT /posts/{id}/status` | only `draft` or `schedule` | controlled transition |
| `PUT /posts/{id}/release-id` | sets release ID | recovery only; middleware must not call ordinarily |
| `GET /analytics/{integration}?date=` | account analytics | analytics |
| `GET /analytics/post/{postId}?date=` | post analytics | analytics |
| `GET /groups` | customer/workspace-like groups | mapping evidence |
| `GET /notifications` | paged organization notifications | failure reconciliation aid |
| `GET /social/{provider}` | generates OAuth URL | human-admin flow only |
| `DELETE /integrations/{id}` | destructive channel removal | explicitly excluded |
| `POST /integration-trigger/{id}` | provider tool dispatch | allowlist required; excluded by default |

Observed limitations: no request idempotency header or persistence; no public `GET /posts/{id}` route (adapter must list a bounded range then match or use the authenticated UI endpoint only if officially supported); only `POST /public/v1/posts` is throttled by the application guard, keyed by organization; the precise configured limit comes from runtime throttler configuration and is not a contractual allowance. Error bodies vary between `{msg}`, validation arrays, and provider validation errors, so normalization is mandatory.

The installed webhooks UI stores public HTTPS destinations per integration. Delivery code exposes no signature, timestamp, replay identifier, or authenticated public-API management endpoint. It is insufficient for the proposed security contract. Use middleware polling reconciliation until a signed adapter callback is implemented.
