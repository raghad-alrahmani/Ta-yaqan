from app import db
from sqlalchemy.sql import func


# =========================
# 1) Admin
# =========================
class Admin(db.Model):
    __tablename__ = "admin"

    adminid = db.Column(db.Integer, primary_key=True)
    adminname = db.Column(db.String(30), nullable=False)
    adminemail = db.Column(db.String(40), nullable=False)
    adminpassword = db.Column(db.String(255), nullable=False)

    reports = db.relationship("Report", backref="admin", lazy=True)


# =========================
# 2) Verifier_User
# =========================
class VerifierUser(db.Model):
    __tablename__ = "verifier_user"

    verifierid = db.Column(db.Integer, primary_key=True)
    verifiername = db.Column(db.String(30), nullable=False)
    verifieremail = db.Column(db.String(40), nullable=False)
    verifierpassword = db.Column(db.String(255), nullable=False)

    inputs = db.relationship("RecitationInput", backref="verifier", lazy=True)
    activities = db.relationship("ActivityLog", backref="verifier", lazy=True)
    target_reports = db.relationship("Report", backref="target_verifier", lazy=True,
                                    foreign_keys="Report.targetverifierid")


# =========================
# 3) Quran_Surah
# =========================
class QuranSurah(db.Model):
    __tablename__ = "quran_surah"

    surahid = db.Column(db.Integer, primary_key=True)
    surahname = db.Column(db.String(50), nullable=False)
    ayahcount = db.Column(db.Integer, nullable=False)

    ayat = db.relationship("QuranAyah", backref="surah", lazy=True)


# =========================
# 4) Quran_Ayah
# =========================
class QuranAyah(db.Model):
    __tablename__ = "quran_ayah"

    # إذا بقاعدة البيانات صار Identity/Auto increment فهنا طبيعي ما تحطين قيمة ويدخل لحاله
    ayahid = db.Column(db.Integer, primary_key=True)

    surahid = db.Column(db.Integer, db.ForeignKey("quran_surah.surahid"), nullable=False)
    ayahnumber = db.Column(db.Integer, nullable=False)
    ayahtext = db.Column(db.Text, nullable=False)

    errors = db.relationship("ErrorDetails", backref="ayah", lazy=True)


# =========================
# 5) Recitation_Inputs
# =========================
class RecitationInput(db.Model):
    __tablename__ = "recitation_inputs"

    inputid = db.Column(db.Integer, primary_key=True)
    verifierid = db.Column(db.Integer, db.ForeignKey("verifier_user.verifierid"), nullable=False)

    inputtype = db.Column(db.Text, nullable=False)
    filepathorlink = db.Column(db.String(255), nullable=False)

    processingdate = db.Column(db.DateTime, nullable=True)
    verificationstatus = db.Column(db.Boolean, nullable=False, server_default=db.text("TRUE"))

    errors = db.relationship("ErrorDetails", backref="input", lazy=True)
    reports = db.relationship("Report", backref="input", lazy=True)


# =========================
# 6) Error_Details
# =========================
class ErrorDetails(db.Model):
    __tablename__ = "error_details"

    errorid = db.Column(db.Integer, primary_key=True)

    inputid = db.Column(db.Integer, db.ForeignKey("recitation_inputs.inputid"), nullable=False)
    referenceayahid = db.Column(db.Integer, db.ForeignKey("quran_ayah.ayahid"), nullable=False)

    errortype = db.Column(db.String(15), nullable=False)
    mismatchedtext = db.Column(db.Text, nullable=False)

    # DECIMAL(8,2)
    errorstarttime = db.Column(db.Numeric(8, 2), nullable=True)
    errorendtime = db.Column(db.Numeric(8, 2), nullable=True)


# =========================
# 7) Reports
# =========================
class Report(db.Model):
    __tablename__ = "reports"

    reportid = db.Column(db.Integer, primary_key=True)

    adminid = db.Column(db.Integer, db.ForeignKey("admin.adminid"), nullable=False)
    targetverifierid = db.Column(db.Integer, db.ForeignKey("verifier_user.verifierid"), nullable=True)
    inputid = db.Column(db.Integer, db.ForeignKey("recitation_inputs.inputid"), nullable=True)

    reporttype = db.Column(db.String(20), nullable=False)

    periodstart = db.Column(db.DateTime, nullable=True)
    periodend = db.Column(db.DateTime, nullable=True)

    generatedat = db.Column(db.DateTime, nullable=False, server_default=func.now())
    filepath = db.Column(db.String(255), nullable=True)


# =========================
# 8) Activity_Log
# =========================
class ActivityLog(db.Model):
    __tablename__ = "activity_log"

    activityid = db.Column(db.Integer, primary_key=True)
    verifierid = db.Column(db.Integer, db.ForeignKey("verifier_user.verifierid"), nullable=False)

    activitytype = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)

