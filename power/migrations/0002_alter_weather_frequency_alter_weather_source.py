# Migration 0002 — no-op (retained for migration history compatibility)
# The original migration referenced an old Weather model that no longer exists.
# The database is pre-seeded; no schema changes are needed here.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('power', '0001_initial'),
    ]

    operations = [
        # Intentionally empty — DB is pre-seeded with db.sqlite3
    ]
