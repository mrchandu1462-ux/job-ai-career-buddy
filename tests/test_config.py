from app.config import settings


def test_config_paths():
    assert settings.base_dir.exists()
    assert settings.profile_file.name == "profile.yaml"
    assert settings.facts_file.name == "facts.yaml"
    assert "Bengaluru" in settings.india_priority_locations
    assert "Design Verification Engineer" in settings.target_roles
