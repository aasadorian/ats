from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

CREATE = """
CREATE OR REPLACE FUNCTION activity_event_append_only() RETURNS trigger AS $$
BEGIN
    IF current_setting('ats.activity_maintenance', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION 'activity_activityevent is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER activity_event_append_only
BEFORE UPDATE OR DELETE ON activity_activityevent
FOR EACH ROW EXECUTE FUNCTION activity_event_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS activity_event_append_only ON activity_activityevent;
DROP FUNCTION IF EXISTS activity_event_append_only();
"""


def create_trigger(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE)


def drop_trigger(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("activity", "0002_initial")]

    operations = [migrations.RunPython(create_trigger, drop_trigger)]
