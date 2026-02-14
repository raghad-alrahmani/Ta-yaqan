import os

class Config:
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:Tayaqan123@localhost:5432/tayaqan_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
