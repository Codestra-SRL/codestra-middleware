# Candidate image SBOMs

These gzip-compressed CycloneDX JSON SBOMs were generated on July 31, 2026
with Syft 1.42.1 from the exact image references recorded in
`../image-security-decision.json`.

Validate them without extracting into the repository:

```sh
sha256sum -c SHA256SUMS
gzip -t *.cdx.json.gz
```

The SBOMs are inventory evidence, not a security acceptance. The image decision
remains blocked until an authorized security owner records an explicit,
time-limited isolated-staging decision.
