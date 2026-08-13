from pathlib import Path


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
