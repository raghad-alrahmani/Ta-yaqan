import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_mail import Mail

db = SQLAlchemy()
mail = Mail()   # لازم يكون خارج الدالة مثل ما عندكم

def create_app():
    # تحميل متغيرات البيئة من .env
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    print(f"Connecting to: {os.getenv('DATABASE_URL')}")# مؤقت

    app = Flask(__name__)

    # ✅ إعدادات المشروع الأساسية (مثل قبل)
    app.config.from_object("app.config.Config")

    # ✅ Override DB URI من Neon (DATABASE_URL)
    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if db_url:
        # بعض الخدمات تعطي postgres:// (SQLAlchemy يبغى postgresql://)
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ✅ مهم عشان flash/session (مثل النسخة الثانية)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # ✅ Mail Config (مثل النسخة الثانية)
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "1") == "1"
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

    # تفعيل الإضافات
    db.init_app(app)
    mail.init_app(app)

    # تسجيل الراوتس (Blueprint)
    from app.routes import main
    app.register_blueprint(main)

    from .auth_routes import auth
    app.register_blueprint(auth)

    # ✅ إنشاء الجداول
    with app.app_context():
        db.create_all()

    return app