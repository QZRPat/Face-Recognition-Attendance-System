from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone
from datetime import date
from sqlalchemy import CheckConstraint
import pytz

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    
def create_default_user():
    default_username = "FRASAdmin"
    default_password = "FRAS2023psuAdmin"
    hashed_password = generate_password_hash(default_password, method='pbkdf2:sha256')
    # Check if the user already exists
    user = User.query.filter_by(username=default_username).first()
    if not user:
        # Create the default user
        default_user = User(username=default_username, password=hashed_password)
        db.session.add(default_user)
        db.session.commit()

class Students(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    lrn = db.Column(db.Integer, unique=True)
    fullName = db.Column(db.String(250))  # Updated attribute name
    grade = db.Column(db.Integer)
    section = db.Column(db.String(120))
    __table_args__ = (
        CheckConstraint('lrn >= 0', name='positive_lrn'),
        )

class AttendanceDB(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullName = db.Column(db.String(250))  # Updated attribute name
    grade = db.Column(db.Integer)
    section = db.Column(db.String(120))
    date_time_taken = db.Column(db.DateTime, default=lambda:datetime.now(pytz.timezone('Asia/Manila')))
    status = db.Column(db.String(20))
'''  
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    present_time = db.Column(db.String(5), nullable=False)
    late_time = db.Column(db.String(5), nullable=False)
    absent_time = db.Column(db.String(5), nullable=False)
'''

class ScheduleB(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    on_timeB = db.Column(db.String(5))
    lateB = db.Column(db.String(5))
    absentB = db.Column(db.String(5))
