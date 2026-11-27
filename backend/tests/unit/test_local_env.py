import pytest

from food_tracker.core.local_env import update_env


def test_env_update_preserves_other_settings_and_round_trips_secret(tmp_path):
    from food_tracker.core.config import Settings

    path = tmp_path / ".env"
    path.write_text(
        "FOOD_TRACKER_ACCESS_JWT_SECRET=kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk\n"
        "# SMTP\nFOOD_TRACKER_SMTP_PASSWORD=old\n"
        "export FOOD_TRACKER_SMTP_PASSWORD=duplicate\n"
        "FOOD_TRACKER_DATABASE_URL=postgresql+psycopg://localhost/test"
    )
    secret_value = "test pass'with\\quotes#="
    update_env(
        path,
        {
            "FOOD_TRACKER_SMTP_PASSWORD": secret_value,
            "FOOD_TRACKER_SMTP_USERNAME": "sender@example.org",
        },
    )
    parsed = Settings(_env_file=path)
    assert parsed.smtp_password.get_secret_value() == secret_value
    assert parsed.access_jwt_secret.get_secret_value() == "k" * 32
    assert str(parsed.database_url) == "postgresql+psycopg://localhost/test"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text().count("FOOD_TRACKER_SMTP_PASSWORD=") == 1


def test_failed_atomic_replace_keeps_existing_env_and_removes_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    original = "FOOD_TRACKER_ACCESS_JWT_SECRET=kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk\n"
    path.write_text(original)

    def failed_replace(*_):
        raise OSError("simulated write failure")

    monkeypatch.setattr("food_tracker.core.local_env.os.replace", failed_replace)
    with pytest.raises(OSError):
        update_env(path, {"FOOD_TRACKER_SMTP_PASSWORD": "local-test-secret"})
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_env_setup_rejects_multiline_values_and_symlink_targets(tmp_path):
    path = tmp_path / ".env"
    with pytest.raises(ValueError):
        update_env(path, {"FOOD_TRACKER_SMTP_PASSWORD": "first\nINJECTED=value"})
    assert not path.exists()
    target = tmp_path / "target"
    target.write_text("unchanged")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        update_env(path, {"FOOD_TRACKER_SMTP_PASSWORD": "test"})
    assert target.read_text() == "unchanged"
