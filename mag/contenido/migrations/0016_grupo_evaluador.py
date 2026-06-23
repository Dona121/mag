from django.db import migrations


def crear_grupo_evaluador(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Evaluador")


def borrar_grupo_evaluador(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Evaluador").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contenido", "0015_alter_periodo_publico"),
    ]

    operations = [
        migrations.RunPython(crear_grupo_evaluador, borrar_grupo_evaluador),
    ]
