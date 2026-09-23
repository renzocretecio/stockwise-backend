"""Prepare the database during a deployment.

Legacy KitaStock databases were initialized with SQLAlchemy metadata rather
than an initial Alembic revision. A new production database is therefore
bootstrapped once and stamped at the current revision. Every later deployment
uses Alembic normally.
"""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config.rbac import PERMISSIONS
from app.config.database import SessionLocal, engine
from app.models import Base, Business, BusinessMembership, Role
from app.models.permission import Permission
from app.services.business import BusinessService


def get_alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    return Config(str(root / "alembic.ini"))


def seed_rbac_data() -> None:
    """Create global permissions and synchronize every business's roles."""
    with SessionLocal() as db:
        permissions = {
            permission.key: permission
            for permission in db.query(Permission).all()
        }

        for key, description in PERMISSIONS.items():
            permission = permissions.get(key)
            if permission:
                permission.description = description
                continue

            db.add(Permission(key=key, description=description))

        db.flush()

        businesses = db.query(Business).all()
        business_roles = {
            business.id: BusinessService.ensure_system_roles(business.id, db)
            for business in businesses
        }

        legacy_memberships = (
            db.query(BusinessMembership, Role.name)
            .join(Role, Role.id == BusinessMembership.role_id)
            .filter(Role.business_id.is_(None))
            .all()
        )
        for membership, legacy_role_name in legacy_memberships:
            role_name = (
                "cashier"
                if legacy_role_name.lower() == "clerk"
                else legacy_role_name.lower()
            )
            role = business_roles[membership.business_id].get(role_name)
            if role:
                membership.role_id = role.id

        db.commit()


def bootstrap_database() -> None:
    """Create the current schema and its required reference data once."""
    Base.metadata.create_all(bind=engine)
    seed_rbac_data()


def baseline_database() -> None:
    """Baseline an existing legacy schema at the current Alembic revision."""
    config = get_alembic_config()
    bootstrap_database()
    command.stamp(config, "head")


def deploy_database() -> None:
    """Bootstrap an unversioned database or upgrade a versioned database."""
    config = get_alembic_config()

    if inspect(engine).has_table("alembic_version"):
        command.upgrade(config, "head")
        seed_rbac_data()
        return

    baseline_database()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Baseline an existing legacy schema at the current revision.",
    )
    args = parser.parse_args()

    if args.baseline:
        baseline_database()
        return

    deploy_database()


if __name__ == "__main__":
    main()
