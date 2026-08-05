# Testing

Backend focused tests and lint/compile checks run in the pinned middleware
image. Frontend `npm ci --legacy-peer-deps` and production build pass with
existing dependency warnings; runtime accessibility/E2E tests require a
staging browser deployment.
