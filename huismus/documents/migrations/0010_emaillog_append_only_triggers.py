# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPEC.md section 4: EmailLog is append-only, "never updated or deleted".
# EmailLog.save()/delete() refuse it; these triggers catch every other path
# to the database (a bulk .update()/.delete(), raw SQL), like the triggers
# for issued documents in 0003.
from django.db import migrations

CREATE_TRIGGERS = """
CREATE TRIGGER documents_emaillog_append_only_update
BEFORE UPDATE ON documents_emaillog
BEGIN
    SELECT RAISE(ABORT, 'Sent e-mails are immutable.');
END;

CREATE TRIGGER documents_emaillog_append_only_delete
BEFORE DELETE ON documents_emaillog
BEGIN
    SELECT RAISE(ABORT, 'Sent e-mails are immutable.');
END;
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS documents_emaillog_append_only_update;
DROP TRIGGER IF EXISTS documents_emaillog_append_only_delete;
"""


class Migration(migrations.Migration):
    dependencies = [("documents", "0009_emaillog")]

    operations = [migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP_TRIGGERS)]
