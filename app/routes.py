from flask import Blueprint, render_template
from app import db
from app.models import VerifierUser

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("landing.html")

@main.route("/about")
def about():
    return render_template("about.html")

@main.route("/add-test")
def add_test():
    email = "test@tayaqan.com"

    existing = VerifierUser.query.filter_by(verifieremail=email).first()
    if existing:
        return "Already exists ✅"

    user = VerifierUser(
        verifiername="Test User",
        verifieremail=email,
        verifierpassword="123"
    )
    db.session.add(user)
    db.session.commit()
    return "Inserted ✅"

