from app.core.config import Settings


def test_high_risk_production_defaults_are_fail_closed():
    settings = Settings()
    assert settings.ai_inference_enabled is False
    assert settings.scraper_real_http_fetch_enabled is False
    assert settings.scraper_browser_enabled is False
    assert settings.scraper_search_connector_enabled is False
    assert settings.odoo_lead_create_enabled is False
    assert settings.odoo_import_production_enabled is False
    assert settings.vicidial_lead_create_enabled is False
    assert settings.vicidial_live_dialing_enabled is False
    assert settings.call_recording_processing_enabled is False
    assert settings.call_analysis_enabled is False
    assert settings.agent_assist_real_audio_enabled is False
    assert settings.agent_assist_automatic_actions_enabled is False
    assert settings.postiz_publishing_enabled is False
    assert settings.automatic_production_activation_enabled is False
