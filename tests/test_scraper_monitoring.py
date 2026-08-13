from pathlib import Path

import yaml


def test_scraper_alerts_have_threshold_owner_and_runbook() -> None:
    alerts = Path("monitoring/middleware-alerts.yaml").read_text()
    for name in (
        "CodestraScraperInboxBacklog",
        "CodestraScraperOldestPending",
        "CodestraScraperDeadLetter",
        "CodestraScraperAuthenticationFailures",
        "CodestraScraperRedisErrors",
    ):
        block = alerts.split(f"alert: {name}", 1)[1].split("- alert:", 1)[0]
        assert "for:" in block
        assert "owner:" in block
        assert "runbook_url:" in block


def test_scraper_alert_transition_matrix_is_present() -> None:
    matrix = yaml.safe_load(Path("monitoring/scraper-alerts.test.yaml").read_text())
    cases = matrix["tests"][0]["alert_rule_test"]
    for name in (
        "CodestraScraperInboxBacklog",
        "CodestraScraperOldestPending",
        "CodestraScraperDeadLetter",
        "CodestraScraperAuthenticationFailures",
        "CodestraScraperRedisErrors",
    ):
        matching = [case for case in cases if case["alertname"] == name]
        assert any(case["exp_alerts"] for case in matching), name
        assert any(not case["exp_alerts"] for case in matching), name
