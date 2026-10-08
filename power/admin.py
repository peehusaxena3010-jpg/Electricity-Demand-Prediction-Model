from django.contrib import admin
from .models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min


@admin.register(ChhattsgarhLoad5Min)
class ChhattsgarhLoad5MinAdmin(admin.ModelAdmin):
    list_display    = ("datetime", "demand_mw", "isgs_mw", "import_mw", "source")
    list_filter     = ("source",)
    search_fields   = ("datetime",)
    date_hierarchy  = "datetime"
    ordering        = ("-datetime",)
    readonly_fields = ("datetime", "demand_mw", "isgs_mw", "import_mw", "source")


@admin.register(ChhattsgarhWeather5Min)
class ChhattsgarhWeather5MinAdmin(admin.ModelAdmin):
    list_display    = ("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms", "source")
    list_filter     = ("source",)
    search_fields   = ("datetime",)
    date_hierarchy  = "datetime"
    ordering        = ("-datetime",)
    readonly_fields = ("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms", "source")
