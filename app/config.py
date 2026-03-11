import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # ✅ Neon first (DATABASE_URL), fallback to local
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or "postgresql+psycopg2://postgres:Tayaqan123@localhost:5432/tayaqan_db"
    )

    # بعض الخدمات تعطي postgres:// بدل postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False 