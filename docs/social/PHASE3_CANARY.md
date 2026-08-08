# Phase 3 canary

The isolated canary implementation is disabled by default. Activation requires certified Phase 2 Postly authentication/health, an approved Hootsuite developer app, successful OAuth refresh, and an explicitly classified staging-safe Hootsuite profile.

Those prerequisites were absent during this run, so no real Hootsuite request and no provider switch occurred. Contract tests use synthetic transports and identities only.
