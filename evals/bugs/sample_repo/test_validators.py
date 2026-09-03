from validators import validate_email


def test_validate_email_rejects_none():
    assert validate_email(None) is False
