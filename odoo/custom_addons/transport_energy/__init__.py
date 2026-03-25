from . import models


def post_init_hook(env):
    """Convertit les colonnes jsonb en varchar après chaque mise à jour."""
    env.cr.execute("""
        ALTER TABLE transport_energy_type
        ALTER COLUMN name TYPE varchar
        USING CASE
            WHEN name::text LIKE '{%' THEN name::jsonb->>'en_US'
            ELSE name::text
        END;
    """)
    env.cr.execute("""
        ALTER TABLE transport_energy_type
        ALTER COLUMN unite TYPE varchar
        USING CASE
            WHEN unite::text LIKE '{%' THEN unite::jsonb->>'en_US'
            ELSE unite::text
        END;
    """)