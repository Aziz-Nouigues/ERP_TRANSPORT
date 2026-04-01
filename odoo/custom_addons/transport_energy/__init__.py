# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Convertit les colonnes jsonb en varchar apres installation."""
    for table, col in [
        ('transport_energy_type', 'name'),
        ('transport_energy_type', 'unite'),
    ]:
        env.cr.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name=%s AND column_name=%s",
            (table, col)
        )
        row = env.cr.fetchone()
        if row and row[0] == 'jsonb':
            env.cr.execute(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE varchar "
                f"USING CASE WHEN {col}::text LIKE '{{%' "
                f"THEN {col}::jsonb->>'en_US' ELSE {col}::text END"
            )
