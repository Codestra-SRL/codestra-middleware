# Identity resolution

Resolution order is explicit mapping, verified social profile, normalized email, normalized E.164 telephone, trusted external reference, then composite evidence. PostgreSQL advisory transaction locks and unique constraints serialize concurrent requests sharing strong keys.

Email normalization trims, applies Unicode normalization, case-folds, and validates syntax without provider-specific alias collapsing. Phone numbers are converted to E.164 only with an explicit international prefix or sufficient country hint; ambiguous numbers remain unresolved.

AI may propose weak textual similarities later, but cannot authorize a merge. Cross-tenant matches are structurally excluded. Conflict results expose only Codestra review references.
