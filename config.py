import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/seats")
APP_ENV = os.getenv("APP_ENV", "local")
