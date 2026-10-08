import os
import joblib
from django.conf import settings

PATH = os.path.join(settings.BASE_DIR, "power", "ml", "models", "modelsTrainData")


def save_model(filename: str, model):
    os.makedirs(PATH, exist_ok=True)
    joblib.dump(model, os.path.join(PATH, filename))


def load_model(filename: str):
    return joblib.load(os.path.join(PATH, filename))



