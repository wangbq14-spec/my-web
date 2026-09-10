"""Exercise the Beta migration against a populated pre-Beta schema."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_beta_migration_preserves_existing_users_and_round_trips():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/f5c6d7e8f9a0_add_beta_foundation.py"
    spec = importlib.util.spec_from_file_location("beta_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "f4b5c6d7e8f9"
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE conversations (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE messages (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'existing')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            row = connection.exec_driver_sql(
                "SELECT username, role, referral_code, referred_by_user_id FROM users"
            ).one()
            assert tuple(row) == ("existing", "user", None, None)
            inspector = sa.inspect(connection)
            assert {"invite_codes", "recharge_requests", "feedback", "message_attachments"} <= set(inspector.get_table_names())
            assert any(item["column_names"] == ["code"] for item in inspector.get_unique_constraints("invite_codes"))
            assert {fk["referred_table"] for fk in inspector.get_foreign_keys("message_attachments")} == {"users", "conversations", "messages"}
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT username FROM users").scalar_one() == "existing"
            assert {column["name"] for column in sa.inspect(connection).get_columns("users")} == {"id", "username"}
            assert not {"invite_codes", "recharge_requests", "feedback", "message_attachments"} & set(sa.inspect(connection).get_table_names())
    engine.dispose()
