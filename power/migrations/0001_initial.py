from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ChhattsgarhLoad5Min",
            fields=[
                ("id",        models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("datetime",  models.DateTimeField(db_index=True, unique=True)),
                ("demand_mw", models.FloatField()),
                ("isgs_mw",   models.FloatField(blank=True, null=True)),
                ("import_mw", models.FloatField(blank=True, null=True)),
                ("source",    models.CharField(
                    choices=[("merit", "Merit India API"), ("historical", "Historical Excel")],
                    default="merit", max_length=20,
                )),
            ],
            options={
                "db_table": "power_chhattsgarhload5min",
                "ordering": ["-datetime"],
                "verbose_name": "Chhattisgarh 5-Min Load",
            },
        ),
        migrations.CreateModel(
            name="ChhattsgarhWeather5Min",
            fields=[
                ("id",            models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("datetime",      models.DateTimeField(db_index=True, unique=True)),
                ("temperature_c", models.FloatField()),
                ("humidity_pct",  models.FloatField(blank=True, null=True)),
                ("rain_mm",       models.FloatField(blank=True, null=True)),
                ("wind_speed_ms", models.FloatField(blank=True, null=True)),
                ("source",        models.CharField(
                    choices=[("open_meteo", "Open-Meteo API"), ("historical", "Historical CSV")],
                    default="open_meteo", max_length=20,
                )),
            ],
            options={
                "db_table": "power_chhattsgarhweather5min",
                "ordering": ["-datetime"],
                "verbose_name": "Chhattisgarh 5-Min Weather",
            },
        ),
    ]
