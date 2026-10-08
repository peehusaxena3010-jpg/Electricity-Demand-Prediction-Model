from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from power.api import router as power_router

api = NinjaAPI(title="Chhattisgarh Demand Forecast API", version="1.0.0")
api.add_router("/", power_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]