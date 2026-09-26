from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (register models)
from app.config import get_settings
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = config.attributes.get("database_url") or get_settings().database_url
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata

POSTGIS_TABLES = {"spatial_ref_sys", "topology", "layer"}
# Created with raw SQL in migrations (partial / expression indexes the ORM does not model)
RAW_SQL_INDEXES = {"ix_rel_live_source", "ix_rel_live_target", "ix_entities_live_type", "ix_entities_label_prefix"}


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    if type_ == "index" and name in RAW_SQL_INDEXES:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, include_object=include_object,
                      process_revision_directives=alembic_helpers.writer, render_item=alembic_helpers.render_item)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:  # noqa: ANN001
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object,
                      process_revision_directives=alembic_helpers.writer, render_item=alembic_helpers.render_item)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
