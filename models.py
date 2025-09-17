from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo

db = SQLAlchemy()

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_code = db.Column(db.String(10), unique=True, nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=True)
    pin = db.Column(db.String(128), nullable=False)
    pin_index = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='colaborador')
    department = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    admission_date = db.Column(db.Date, nullable=True)
    unit = db.Column(db.String(50), nullable=True)
    position = db.Column(db.String(50), nullable=True)
    photo_url = db.Column(db.String(255), nullable=True)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    type = db.Column(db.String(50), nullable=True)
    start_datetime = db.Column(db.DateTime, nullable=True)
    end_datetime = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.String(500), nullable=False)
    date = db.Column(db.Date, nullable=False)
    project = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(50), nullable=True)
    weekday = db.Column(db.String(20), nullable=True)
    is_edited = db.Column(db.Boolean, nullable=False, default=False)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    report_number = db.Column(db.String(20), nullable=False)
    period = db.Column(db.String(7), nullable=False)
    format = db.Column(db.String(10), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(ZoneInfo("America/Sao_Paulo")))
    signature_status = db.Column(db.String(50), nullable=True, default='Pendente')

class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    icj_contract = db.Column(db.String(50), nullable=False)
    sap_contract = db.Column(db.String(50), nullable=False)
    fiscal = db.Column(db.String(100), nullable=False)
    field_fiscal = db.Column(db.String(100), nullable=False)
    manager = db.Column(db.String(100), nullable=True)