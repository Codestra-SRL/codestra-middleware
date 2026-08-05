from app.core.trading_pilot import (
    KillSwitch,
    PilotAdmission,
    activate_kill_switch,
    admit_pilot,
    validate_classification,
)


def test_business_model_classifications_are_explicit():
    assert validate_classification("INTENDED") == "INTENDED"


def test_pilot_requires_all_approvals_and_synthetic_only():
    assert admit_pilot(PilotAdmission("tenant-a", "acct-a", True, True, True, True)) is True
    assert admit_pilot(PilotAdmission("tenant-a", "acct-a", False, True, True, True)) is False


def test_kill_switch_requires_privileged_reason_and_disabled_paths():
    assert activate_kill_switch(KillSwitch("risk incident", True, True, True)) is True
    assert activate_kill_switch(KillSwitch("", True, True, True)) is False
