"""Same object filter as migrations/env.py (PostGIS internals and raw-SQL partial indexes)."""
from geoalchemy2 import alembic_helpers

POSTGIS_TABLES = {"spatial_ref_sys", "topology", "layer"}
RAW_SQL_INDEXES = {"ix_rel_live_source", "ix_rel_live_target", "ix_entities_live_type", "ix_entities_label_prefix"}


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    if type_ == "index" and name in RAW_SQL_INDEXES:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)
