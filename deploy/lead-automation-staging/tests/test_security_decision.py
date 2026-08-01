from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lead_staging_security_decision", ROOT / "security_decision.py"
)
assert SPEC is not None and SPEC.loader is not None
SECURITY_DECISION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SECURITY_DECISION)
validate_decision = SECURITY_DECISION.validate_decision
validate_external = SECURITY_DECISION.validate_external

UTC = dt.timezone(dt.timedelta())


class DecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = json.loads(
            (ROOT / "security/image-security-decision.json").read_text()
        )
        cls.counts = json.loads(
            (ROOT / "security/vulnerability-counts.json").read_text()
        )
        cls.policy_sha = hashlib.sha256(
            (ROOT / "security/image-verification-policy.json").read_bytes()
        ).hexdigest()
        cls.now = dt.datetime(2026, 7, 31, 23, 30, tzinfo=UTC)

    def errors(self, **changes):
        value = copy.deepcopy(self.decision)
        value.update(changes)
        return validate_decision(value, self.now, self.policy_sha, self.counts)

    def test_valid_decision_required(self):
        self.assertEqual(self.errors(), [])

    def test_unknown_status(self):
        self.assertTrue(self.errors(status="unknown"))

    def test_unknown_property(self):
        self.assertTrue(self.errors(extra=True))

    def test_negative_authorizations(self):
        for name in (
            "production_deployment_gate",
            "production_activation_gate",
            "server_b_access_gate",
            "customer_data_gate",
        ):
            self.assertTrue(self.errors(**{name: "allowed"}))

    def approved(self):
        value = copy.deepcopy(self.decision)
        value.update(
            status="approved_for_staging",
            security_owner_acceptance_present=True,
            approved_scope="server_a_isolated_staging",
            security_owner="owner",
            security_owner_authority_reference="github://org/security-team",
            decision_timestamp_utc="2026-07-31T23:00:00Z",
            expiration_timestamp_utc="2026-08-15T23:00:00Z",
            approval_reference="github://issue/1",
            accepted_image_digests={k: v["digest"] for k, v in self.counts.items()},
            accepted_vulnerability_counts=self.counts,
            required_compensating_controls=["private-network"],
            revocation_conditions=["digest-change"],
        )
        return value

    def test_approved_matrix(self):
        good = self.approved()
        self.assertEqual(
            validate_decision(good, self.now, self.policy_sha, self.counts), []
        )
        for field in (
            "security_owner",
            "security_owner_authority_reference",
            "required_compensating_controls",
        ):
            bad = copy.deepcopy(good)
            bad[field] = None
            self.assertTrue(
                validate_decision(bad, self.now, self.policy_sha, self.counts)
            )
        bad = copy.deepcopy(good)
        bad["accepted_image_digests"]["n8n"] = "n8n:latest"
        self.assertTrue(validate_decision(bad, self.now, self.policy_sha, self.counts))
        bad = copy.deepcopy(good)
        bad["accepted_vulnerability_counts"]["n8n"]["trivy_high"] = 7
        self.assertTrue(validate_decision(bad, self.now, self.policy_sha, self.counts))
        bad = copy.deepcopy(good)
        bad["expiration_timestamp_utc"] = "2026-07-30T00:00:00Z"
        self.assertTrue(validate_decision(bad, self.now, self.policy_sha, self.counts))

    def test_external_separation(self):
        decision = self.approved()
        record = {
            "record_type": "code_review",
            "security_owner": "owner",
            "authority_reference": "github://team",
            "pr_head": "a" * 40,
            "image_digests": decision["accepted_image_digests"],
            "vulnerability_counts": decision["accepted_vulnerability_counts"],
            "scope": "server_a_isolated_staging",
            "decision": "accepted",
            "decision_timestamp_utc": "2026-07-31T23:00:00Z",
            "expiration_timestamp_utc": "2026-08-15T23:00:00Z",
            "immutable_reference": "github://review/1",
            "created_at_utc": "2026-07-31T23:00:00Z",
            "updated_at_utc": "2026-07-31T23:00:00Z",
            "signer_identity": "https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/security-owner-decision-sign.yml@refs/heads/main",
            "signer_oidc_issuer": "https://token.actions.githubusercontent.com",
            "decision_signature_bundle": "/evidence/security-decision.bundle.json",
        }
        self.assertTrue(validate_external(record, decision, "a" * 40, self.now))
        record["record_type"] = "security_risk_acceptance"
        record["updated_at_utc"] = "2026-08-01T00:00:00Z"
        self.assertTrue(validate_external(record, decision, "a" * 40, self.now))

    def test_decision_required_cannot_populate_approval_fields(self):
        self.assertTrue(self.errors(security_owner="source-author"))
        self.assertTrue(self.errors(security_owner_acceptance_present=True))

    def test_approved_timestamp_order_and_expiry(self):
        value = self.approved()
        value["expiration_timestamp_utc"] = value["decision_timestamp_utc"]
        self.assertTrue(
            validate_decision(value, self.now, self.policy_sha, self.counts)
        )
        value = self.approved()
        value["expiration_timestamp_utc"] = "2026-07-31T23:15:00Z"
        self.assertTrue(
            validate_decision(value, self.now, self.policy_sha, self.counts)
        )

    def test_external_head_digest_count_owner_and_authority_binding(self):
        decision = self.approved()
        record = {
            "record_type": "security_risk_acceptance",
            "security_owner": decision["security_owner"],
            "authority_reference": decision["security_owner_authority_reference"],
            "pr_head": "a" * 40,
            "image_digests": decision["accepted_image_digests"],
            "vulnerability_counts": decision["accepted_vulnerability_counts"],
            "scope": decision["approved_scope"],
            "decision": "accepted",
            "decision_timestamp_utc": decision["decision_timestamp_utc"],
            "expiration_timestamp_utc": decision["expiration_timestamp_utc"],
            "immutable_reference": "github://security/decision/1",
            "created_at_utc": decision["decision_timestamp_utc"],
            "updated_at_utc": decision["decision_timestamp_utc"],
            "signer_identity": "https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/security-owner-decision-sign.yml@refs/heads/main",
            "signer_oidc_issuer": "https://token.actions.githubusercontent.com",
            "decision_signature_bundle": "/evidence/security-decision.bundle.json",
        }
        self.assertEqual(validate_external(record, decision, "a" * 40, self.now), [])
        for field, replacement in (
            ("pr_head", "b" * 40),
            ("security_owner", "other"),
            ("authority_reference", "github://other"),
            ("scope", "production"),
        ):
            changed = copy.deepcopy(record)
            changed[field] = replacement
            self.assertTrue(validate_external(changed, decision, "a" * 40, self.now))
        for field in ("signer_identity", "signer_oidc_issuer", "decision_signature_bundle"):
            changed = copy.deepcopy(record)
            changed[field] = "invalid"
            self.assertTrue(validate_external(changed, decision, "a" * 40, self.now))


if __name__ == "__main__":
    unittest.main()
