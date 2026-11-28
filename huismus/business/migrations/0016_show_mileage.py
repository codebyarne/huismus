from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0015_show_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="show_mileage",
            field=models.BooleanField(default=False, verbose_name="Kilometers"),
        ),
    ]
