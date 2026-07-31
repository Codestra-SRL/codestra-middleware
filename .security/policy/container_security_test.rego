package main

import rego.v1

test_rejects_mutable_compose_image if {
  result := deny with input as {"services": {"db": {"image": "postgres:17"}}}
  count(result) >= 1
}

test_accepts_hardened_digest_pinned_compose_image if {
  result := deny with input as {"services": {"db": {"image": "postgres@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "read_only": true, "user": "10001:10001", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"]}}}
  count(result) == 0
}

test_rejects_privileged_kubernetes_container if {
  result := deny with input as {"spec": {"template": {"spec": {"containers": [{"image": "redis@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "securityContext": {"privileged": true}}]}}}}
  count(result) >= 1
}

test_rejects_public_compose_port if {
  result := deny with input as {"services": {"app": {"image": "example.invalid/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "read_only": true, "user": "10001", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "ports": ["0.0.0.0:8080:8080"]}}}
  count(result) >= 1
}
