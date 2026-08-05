# Section 12 release runbook

1. Create the change record and release version.
2. Pin artifact, checksum, SBOM, and rollback target.
3. Verify backups and isolated restore evidence.
4. Run mandatory tests and tenant/workspace isolation checks.
5. Validate feature-flag snapshot and maintenance notice.
6. Obtain distinct release, security, rollback, and executive approvals.
7. Deploy to staging and run acceptance checks.
8. Execute bounded canary or blue/green rehearsal where applicable.
9. Submit certification evidence; do not activate production.
10. After separate approval, execute the approved window, monitor, and record
    post-deployment acceptance.
11. If thresholds fail, stop new work and use the rehearsed rollback procedure.
12. Complete the post-implementation review and archive evidence.
