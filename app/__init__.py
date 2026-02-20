import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_mail import Mail

db = SQLAlchemy()
mail = Mail()   # لازم يكون خارج الدالة مثل ما عندكم

def create_app():
    # تحميل متغيرات البيئة من .env
    load_dotenv()

    app = Flask(__name__)

    # ✅ إعدادات المشروع الأساسية (مثل قبل)
    app.config.from_object("app.config.Config")

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

    # ✅ إنشاء الجداول (مثل النسخة الأولى)
    with app.app_context():
        db.create_all()

    return app