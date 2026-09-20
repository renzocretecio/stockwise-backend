from unittest.mock import Mock

import app.jobs.deploy_database as deployment


def test_unversioned_database_is_bootstrapped_and_stamped(monkeypatch):
    inspector = Mock()
    inspector.has_table.return_value = False

    monkeypatch.setattr(deployment, "inspect", lambda _engine: inspector)
    baseline = Mock()
    monkeypatch.setattr(deployment, "baseline_database", baseline)

    deployment.deploy_database()

    baseline.assert_called_once_with()


def test_versioned_database_uses_normal_alembic_upgrade(monkeypatch):
    config = object()
    inspector = Mock()
    inspector.has_table.return_value = True
    bootstrap = Mock()
    upgrade = Mock()

    monkeypatch.setattr(deployment, "get_alembic_config", lambda: config)
    monkeypatch.setattr(deployment, "inspect", lambda _engine: inspector)
    monkeypatch.setattr(deployment, "bootstrap_database", bootstrap)
    monkeypatch.setattr(deployment.command, "upgrade", upgrade)

    deployment.deploy_database()

    bootstrap.assert_not_called()
    upgrade.assert_called_once_with(config, "head")


def test_baseline_creates_current_schema_and_stamps_head(monkeypatch):
    config = object()
    bootstrap = Mock()
    stamp = Mock()

    monkeypatch.setattr(deployment, "get_alembic_config", lambda: config)
    monkeypatch.setattr(deployment, "bootstrap_database", bootstrap)
    monkeypatch.setattr(deployment.command, "stamp", stamp)

    deployment.baseline_database()

    bootstrap.assert_called_once_with()
    stamp.assert_called_once_with(config, "head")
