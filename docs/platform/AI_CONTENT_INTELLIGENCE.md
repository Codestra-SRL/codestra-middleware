# AI content intelligence

`CdstSocialContentGenerateV1` requests Middleware AI routing for English, Spanish, French and Haitian Creole variants, then requires risk review and human approval. AI receives minimized inputs; secrets and direct contact fields are excluded. Results never publish automatically.

Risk outcomes are `PASS`, `REVIEW_REQUIRED`, or `BLOCKED`. Financial, medical, PII, unsafe URL, spam and brand-policy checks are adapter-independent extension points.
