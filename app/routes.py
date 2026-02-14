from flask import Blueprint
from app import db
from app.models import VerifierUser

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return "Ta’yaqan is running 🚀"

@main.route("/add-test")
def add_test():
    user = VerifierUser(
        name="Test User",
        email="test@tayaqan.com",
        password="123"
    )
    db.session.add(user)
    db.session.commit()
    return "Inserted ✅"
