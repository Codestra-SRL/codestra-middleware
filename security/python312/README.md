# Python 3.12 release security backports

The middleware runtime is Python 3.12.14. The Docker build verifies the
official source archive and every remaining upstream backport by SHA-256 before
compiling. Findings fixed by the 3.12.14 release are no longer carried as
local patches.

| Finding | Resolution |
| --- | --- |
| CVE-2026-3644 | CPython maintained-branch backport `dae4b1a21f8df4570e30986affd61bbe4ade4cef` |
| CVE-2026-4224 | CPython maintained-branch backport `642865ddf4b232da1f3b1f7abcfa3254c4bfe785` |
| CVE-2026-7210 | Expat 2.8.3 plus the minimal 3.12 structure adaptation and remaining upstream `fc9b11ff49cbc82e6f917d07a61517a2b5f3145f` changes |

The local Expat patch contains only the version-layout adaptation needed for
Python 3.12. Release evidence must bind the resulting image digest to a VEX
statement for each generic CPE match; the version string alone does not
communicate these source backports to Grype.
