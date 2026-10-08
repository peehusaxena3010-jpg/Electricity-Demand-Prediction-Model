from django.db import models


class ChhattsgarhLoad5Min(models.Model):
    """
    5-minute interval electricity demand data for Chhattisgarh.
    Sources: Merit India API (live) + Historical Excel (2023-2026)
    """
    SOURCE_CHOICES = [
        ("merit",      "Merit India API"),
        ("historical", "Historical Excel"),
    ]

    datetime   = models.DateTimeField(unique=True, db_index=True)
    demand_mw  = models.FloatField()
    isgs_mw    = models.FloatField(null=True, blank=True)
    import_mw  = models.FloatField(null=True, blank=True)
    source     = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="merit")

    class Meta:
        db_table = "power_chhattsgarhload5min"
        ordering = ["-datetime"]
        verbose_name = "Chhattisgarh 5-Min Load"
        verbose_name_plural = "Chhattisgarh 5-Min Loads"

    def __str__(self):
        return f"{self.datetime} | {self.demand_mw} MW"


class ChhattsgarhWeather5Min(models.Model):
    """
    5-minute interval weather data for Chhattisgarh.
    Sources: Open-Meteo API (live) + Historical CSV (2023-2026)
    """
    SOURCE_CHOICES = [
        ("open_meteo", "Open-Meteo API"),
        ("historical", "Historical CSV"),
    ]

    datetime       = models.DateTimeField(unique=True, db_index=True)
    temperature_c  = models.FloatField()
    humidity_pct   = models.FloatField(null=True, blank=True)
    rain_mm        = models.FloatField(null=True, blank=True)
    wind_speed_ms  = models.FloatField(null=True, blank=True)
    source         = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="open_meteo")

    class Meta:
        db_table = "power_chhattsgarhweather5min"
        ordering = ["-datetime"]
        verbose_name = "Chhattisgarh 5-Min Weather"
        verbose_name_plural = "Chhattisgarh 5-Min Weather"

    def __str__(self):
        return f"{self.datetime} | {self.temperature_c}°C"
