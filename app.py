from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
import json
import os
import calendar
import pandas as pd
from io import BytesIO, StringIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import sqlalchemy
from sqlalchemy import inspect
import csv
import traceback
import base64
from PyPDF2 import PdfReader, PdfWriter, Transformation
from PIL import Image as PILImage
import io
from calendar import monthrange
from flask_mail import Mail, Message
import logging
from sqlalchemy.exc import OperationalError, IntegrityError
from time import time
from hashlib import sha256
from scheduler import init_scheduler
from models import db, Employee, Unit, Report, Activity 
from zoneinfo import ZoneInfo

# Configurar logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mapeamento de dias da semana em português
WEEKDAYS_PT = {  # noqa: E701
    0: 'segunda-feira',
    1: 'terça-feira',
    2: 'quarta-feira',
    3: 'quinta-feira',
    4: 'sexta-feira',
    5: 'sábado',
    6: 'domingo'
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/rdat_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['REPORT_FOLDER'] = 'static/reports'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Exemplo: SMTP do Gmail
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER', 'seuemail@example.com')  # Use variável de ambiente
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS', 'sua-senha')  # Use variável de ambiente
mail = Mail(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

logger.debug("Iniciando app.py, IntegrityError importado: %s", IntegrityError)

# Modelos do banco de dados
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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    signature_status = db.Column(db.String(50), nullable=True, default='Pendente')

class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    icj_contract = db.Column(db.String(50), nullable=False)
    sap_contract = db.Column(db.String(50), nullable=False)
    fiscal = db.Column(db.String(100), nullable=False)
    field_fiscal = db.Column(db.String(100), nullable=False)
    manager = db.Column(db.String(100), nullable=True)

# Função auxiliar para obter dias do mês
def get_days_in_month(year, month):
    _, last_day = calendar.monthrange(year, month)
    weekdays = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    days = []
    for day in range(1, last_day + 1):
        date_obj = date(year, month, day)
        days.append({
            'day': day,
            'weekday': weekdays[date_obj.weekday()]
        })
    return days

def create_employer_accounts():
    with app.app_context():
        if not Employee.query.filter_by(email='rh@accerth.com').first():
            rh_employer = Employee(
                email='rh@accerth.com',
                pin=generate_password_hash('rh_acc2025'),
                name='RH Accerth',
                role='empregador',
                department='RH',
                phone='11 99999-0001',
                photo_url=None
            )
            db.session.add(rh_employer)
        if not Employee.query.filter_by(email='suporteti@accerth.com').first():
            ti_employer = Employee(
                email='suporteti@accerth.com',
                pin=generate_password_hash('ti_acc2025'),
                name='Suporte TI Accerth',
                role='empregador',
                department='TI',
                phone='11 99999-0002',
                photo_url=None
            )
            db.session.add(ti_employer)
        try:
            db.session.commit()
            print("Contas de empregadores criadas com sucesso.")
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao criar contas de empregadores: {str(e)}")

def import_employees_from_json(json_file_path):
    with app.app_context():
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                employees_data = json.load(f)
            unique_units = set(emp_data.get('Unidade') for emp_data in employees_data if emp_data.get('Unidade'))
            print(f"Unidades encontradas no JSON: {unique_units}")
            for unit_name in unique_units:
                if not Unit.query.filter_by(name=unit_name).first():
                    unit = Unit(
                        name=unit_name,
                        icj_contract=f"ICJ_{unit_name.replace(' ', '_').replace('(', '').replace(')', '')}",
                        sap_contract=f"SAP_{unit_name.replace(' ', '_').replace('(', '').replace(')', '')}",
                        fiscal=f"Fiscal {unit_name}",
                        field_fiscal=f"Field {unit_name}"
                    )
                    db.session.add(unit)
                    print(f"Unidade adicionada à tabela Unit: {unit_name}")
            db.session.commit()
            for emp_data in employees_data:
                print(f"Dados do JSON: {emp_data}")
                if not Employee.query.filter(
                    (Employee.employer_code == emp_data.get('Matrícula')) |
                    (Employee.email == emp_data.get('email'))
                ).first():
                    admission_date = None
                    if emp_data.get('Data Admissão'):
                        try:
                            admission_date = datetime.strptime(emp_data.get('Data Admissão'), '%d/%m/%Y').date()
                            print(f"Data Admissão convertida: {admission_date} para {emp_data.get('nome')}")
                        except ValueError as e:
                            print(f"Erro ao converter admission_date para {emp_data.get('nome')}: {str(e)}")
                    employee = Employee(
                        employer_code=emp_data.get('Matrícula'),
                        email=emp_data.get('email'),
                        pin=generate_password_hash(emp_data.get('pin', 'default_pin_2025')),
                        name=emp_data.get('nome'),
                        role='colaborador',
                        department=emp_data.get('department'),
                        phone=emp_data.get('phone'),
                        admission_date=admission_date,
                        unit=emp_data.get('Unidade'),
                        position=emp_data.get('Função'),
                        photo_url=None
                    )
                    db.session.add(employee)
                    print(f"Colaborador adicionado: {employee.name}, Unidade: {employee.unit}, Data Admissão: {employee.admission_date}, Função: {employee.position}")
            db.session.commit()
            print(f"Colaboradores e unidades importados com sucesso de {json_file_path}")
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao importar colaboradores ou unidades: {str(e)}")

@app.route('/')
def index():
    print(f"Verificando sessão em /index: {dict(session)}")
    if 'employee_id' in session:
        print(f"Redirecionando com base no role: {session['role']}")
        if session['role'] == 'empregador':
            return redirect(url_for('home'))
        elif session['role'] == 'fiscal':
            return redirect(url_for('home_fiscal'))
        elif session['role'] == 'preposto':
            return redirect(url_for('home_preposto'))
        return redirect(url_for('home_funcionario'))
    print("Renderizando login.html")
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    identifier = request.form['employer_code'].strip()
    pin = request.form['pin'].strip()
    role = request.form['role'].strip()
    
    # Mapear 'colaborador' do formulário para 'funcionario' no banco
    if role == 'colaborador':
        role = 'funcionario'
    
    logger.info(f"Tentativa de login: identifier={identifier}, pin={pin}, role={role}")
    employee = None
    if role == 'funcionario':
        employee = Employee.query.filter_by(employer_code=identifier, role=role).first()
    else:
        employee = Employee.query.filter_by(email=identifier, role=role).first()
    
    if employee:
        logger.info(f"Funcionário encontrado: employer_code={employee.employer_code}, name={employee.name}, role={employee.role}")
        if check_password_hash(employee.pin, pin):
            logger.info(f"Login bem-sucedido: employee_id={employee.id}, role={employee.role}")
            session['employee_id'] = employee.id
            session['employee_name'] = employee.name
            session['role'] = employee.role
            session['department'] = employee.department
            session['unit'] = employee.unit if role in ['fiscal', 'preposto'] else None
            if role == 'empregador':
                return redirect(url_for('home'))
            elif role == 'fiscal':
                return redirect(url_for('home_fiscal'))
            elif role == 'preposto':
                return redirect(url_for('home_preposto'))
            return redirect(url_for('home_funcionario'))
        else:
            logger.error(f"PIN inválido para identifier={identifier}, role={role}")
            flash('E-mail/Código, PIN ou tipo de usuário inválido!', 'error')
    else:
        logger.error(f"Nenhum funcionário encontrado para identifier={identifier}, role={role}")
        flash('E-mail/Código, PIN ou tipo de usuário inválido!', 'error')
    
    return redirect(url_for('index'))

@app.route('/home_funcionario', methods=['GET'])
def home_funcionario():
    if 'employee_id' not in session:
        logger.warning("Tentativa de acesso a /home_funcionario sem login")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    
    if session['role'] != 'funcionario':
        logger.warning(f"Usuário com role {session['role']} tentou acessar /home_funcionario")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    logger.info(f"Acessando /home_funcionario para employee_id={session['employee_id']}, role={session['role']}")
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        logger.error("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('index'))
    
    # Buscar informações da unidade
    unit = Unit.query.filter_by(name=employee.unit).first()
    
    employee_name = employee.name
    employee_data = {
        'name': employee.name,
        'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
        'position': employee.position or 'N/A',
        'unit': employee.unit or 'N/A',
        'manager': unit.manager if unit else '',
        'fiscal': unit.fiscal if unit else '',
        'field_fiscal': unit.field_fiscal if unit else ''
    }
    photo_url = employee.photo_url
    
    return render_template('home_funcionario.html',
                           employee_name=employee_name,
                           employee_data=employee_data,
                           photo_url=photo_url)

@app.route('/save_supervisors', methods=['POST'])
def save_supervisors():
    if 'employee_id' not in session or session['role'] != 'colaborador':
        print("Erro: acesso não autorizado para salvar supervisores")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        print("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('home_funcionario'))
    
    unit = Unit.query.filter_by(name=employee.unit).first()
    if not unit:
        print("Erro: unidade não encontrada")
        flash('Unidade não encontrada.', 'error')
        return redirect(url_for('home_funcionario'))
    
    manager = request.form.get('manager', '').strip()
    fiscal = request.form.get('fiscal', '').strip()
    field_fiscal = request.form.get('field_fiscal', '').strip()

    # Validação de entrada
    if not all([manager, fiscal, field_fiscal]):
        flash('Todos os campos (Gerente, Fiscal, Fiscal de Campo) são obrigatórios!', 'error')
        return redirect(url_for('home_funcionario'))

    try:
        unit.manager = manager
        unit.fiscal = fiscal
        unit.field_fiscal = field_fiscal
        db.session.commit()
        print(f"Supervisores salvos para unidade {unit.name}: Gerente={manager}, Fiscal={fiscal}, Fiscal de Campo={field_fiscal}")
        flash('Informações de supervisores salvas com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar supervisores: {str(e)}")
        flash(f'Erro ao salvar supervisores: {str(e)}.', 'error')
    
    return redirect(url_for('home_funcionario'))

@app.route('/upload_photo', methods=['POST'])
def upload_photo():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'colaborador':
        print("Erro: acesso não autorizado para upload de foto")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Upload de foto para employee_id: {session.get('employee_id')}")
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        print("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('home_funcionario'))
    
    if 'photo' not in request.files:
        print("Erro: nenhuma foto selecionada")
        flash('Nenhuma foto selecionada.', 'error')
        return redirect(url_for('home_funcionario'))
    
    file = request.files['photo']
    if file.filename == '':
        print("Erro: nenhuma foto selecionada")
        flash('Nenhuma foto selecionada.', 'error')
        return redirect(url_for('home_funcionario'))
    
    if file:
        try:
            allowed_extensions = {'png', 'jpg', 'jpeg'}
            if not '.' in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
                print("Erro: extensão de arquivo não permitida")
                flash('Apenas arquivos PNG, JPG ou JPEG são permitidos.', 'error')
                return redirect(url_for('home_funcionario'))
            
            filename = secure_filename(f"employee_{employee.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file.filename.rsplit('.', 1)[1].lower()}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            employee.photo_url = url_for('static', filename=f'uploads/{filename}')
            db.session.commit()
            print(f"Foto salva: {file_path}, photo_url atualizado: {employee.photo_url}")
            flash('Foto atualizada com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar foto: {str(e)}")
            flash(f'Erro ao salvar foto: {str(e)}', 'error')
    
    return redirect(url_for('home_funcionario'))

@app.route('/logout', methods=['GET'])
def logout():
    print(f"Logout para employee_id: {session.get('employee_id')}, role: {session.get('role')}")
    session_data = dict(session)  # Copia a sessão para depuração
    print(f"Sessão antes de limpar: {session_data}")
    session.clear()
    print(f"Sessão após limpar: {dict(session)}")
    flash('Você foi desconectado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/home')
def home():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado à tela inicial")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando home para employee_id: {session.get('employee_id')}")
    employees = Employee.query.filter_by(role='funcionario').all()
    print(f"Funcionários encontrados: {len(employees)}")  # Depuração
    for emp in employees:
        print(f"Nome: {emp.name}, Código: {emp.employer_code}")
    
    return render_template(
        'home.html',
        employee_name=session['employee_name'],
        role=session['role'],
        employees=employees
    )

@app.route('/employees', methods=['GET'])
def employees():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado à lista de funcionários")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando employees para employee_id: {session.get('employee_id')}")
    search_query = request.args.get('search', '').lower()
    employees = Employee.query.filter_by(role='funcionario')
    
    if search_query:
        employees = employees.filter(
            (Employee.name.ilike(f'%{search_query}%')) |
            (Employee.employer_code.ilike(f'%{search_query}%')) |
            (Employee.unit.ilike(f'%{search_query}%'))
        )
    
    employees = employees.order_by(Employee.name).all()
    return render_template('employees.html', 
                           employee_name=session['employee_name'], 
                           role=session['role'],
                           employees=employees,
                           search_query=search_query)

@app.route('/delete_employee/<employer_code>', methods=['POST'])
def delete_employee(employer_code):
    if 'employee_id' not in session:
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403
    
    try:
        employee = Employee.query.filter_by(employer_code=employer_code).first()
        if not employee:
            return jsonify({'success': False, 'message': 'Funcionário não encontrado.'}), 404
        
        # Verificar se o funcionário tem relatórios associados (se aplicável)
        reports = Report.query.filter_by(employee_id=employee.id).count()
        if reports > 0:
            return jsonify({
                'success': False,
                'message': 'Não é possível excluir o funcionário pois há relatórios associados.'
            }), 400
        
        db.session.delete(employee)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Funcionário excluído com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao excluir funcionário: {str(e)}'}), 500

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    start_time = time()
    if 'employee_id' not in session:
        logger.warning("Tentativa de acesso a /add_employee sem login.")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        logger.warning(f"Usuário com role {session['role']} tentou acessar /add_employee.")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    try:
        units = Unit.query.all()
        logger.debug(f"Unidades carregadas: {[unit.name for unit in units]}")
    except OperationalError as e:
        logger.error(f"Erro ao carregar unidades: {str(e)}")
        flash('Erro ao acessar o banco de dados. Verifique a configuração.', 'error')
        return render_template('add_employee.html', employee_name=session['employee_name'], units=[])

    if request.method == 'POST':
        employer_code = request.form.get('employer_code')
        name = request.form.get('name')
        admission_date = request.form.get('admission_date')
        position = request.form.get('position')
        unit = request.form.get('unit')
        pin = request.form.get('pin')

        logger.debug(f"Dados recebidos: employer_code={employer_code}, name={name}, admission_date={admission_date}, position={position}, unit={unit}, pin={'*' * len(pin) if pin else None}")

        if not all([employer_code, name, admission_date, position, unit, pin]):
            logger.warning("Campos obrigatórios não preenchidos.")
            flash('Os campos matrícula, nome, data de admissão, função, unidade e PIN são obrigatórios.', 'error')
            return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

        try:
            # Verificar duplicatas na matrícula
            logger.debug("Verificando matrícula existente...")
            existing_employee = Employee.query.filter_by(employer_code=employer_code).first()
            if existing_employee:
                logger.warning(f"Matrícula já cadastrada: {employer_code}")
                flash('Esta matrícula já está cadastrada.', 'error')
                return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

            # Verificar duplicatas no PIN
            logger.debug("Verificando PIN existente...")
            existing_employees = Employee.query.all()
            for emp in existing_employees:
                if check_password_hash(emp.pin, pin):
                    logger.warning(f"PIN já cadastrado para employer_code: {emp.employer_code}")
                    flash('Este PIN já está cadastrado.', 'error')
                    return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

            # Validar data de admissão
            try:
                admission_date = datetime.strptime(admission_date, '%Y-%m-%d').date() if admission_date else None
            except ValueError:
                logger.warning("Formato de data inválido.")
                flash('Formato de data inválido! Use AAAA-MM-DD.', 'error')
                return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

            logger.debug("Gerando hash do PIN...")
            pin_hash = generate_password_hash(pin, method='pbkdf2:sha256', salt_length=8)
            logger.debug("Criando novo funcionário...")
            employee = Employee(
                employer_code=employer_code,
                name=name,
                admission_date=admission_date,
                position=position,
                unit=unit,
                pin=pin_hash,
                role='funcionario'
            )
            logger.debug("Adicionando funcionário ao banco...")
            db.session.add(employee)
            logger.debug("Executando commit...")
            db.session.commit()
            logger.info(f"Funcionário cadastrado com sucesso: {employer_code}")
            logger.debug(f"Tempo de execução /add_employee: {time() - start_time:.3f}s")
            flash('Funcionário cadastrado com sucesso!', 'success')
            return redirect(url_for('employees'))
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Erro de integridade ao cadastrar funcionário: {str(e)}")
            flash('Erro: PIN ou matrícula já cadastrada.', 'error')
            return render_template('add_employee.html', employee_name=session['employee_name'], units=units)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao cadastrar funcionário: {str(e)}")
            flash(f'Erro ao cadastrar funcionário: {str(e)}', 'error')
            return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

    logger.debug(f"Tempo de execução /add_employee (GET): {time() - start_time:.3f}s")
    return render_template('add_employee.html', employee_name=session['employee_name'], units=units)

# Rota para Verificar PIN
@app.route('/check_pin', methods=['POST'])
def check_pin():
    start_time = time()
    if 'employee_id' not in session:
        logger.warning("Tentativa de acesso a /check_pin sem login.")
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        logger.warning(f"Usuário com role {session['role']} tentou acessar /check_pin.")
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403
    pin = request.json.get('pin')
    if not pin:
        logger.warning("PIN não fornecido na requisição /check_pin.")
        return jsonify({'success': False, 'message': 'PIN não fornecido.'}), 400
    try:
        pin_index = sha256(pin.encode('utf-8')).hexdigest()
        logger.debug(f"Verificando PIN com pin_index: {pin_index}")
        existing_employee = Employee.query.filter_by(pin_index=pin_index).first()
        if existing_employee:
            logger.debug(f"PIN já cadastrado: {pin}, encontrado para employer_code: {existing_employee.employer_code}")
            logger.debug(f"Tempo de execução /check_pin: {time() - start_time:.3f}s")
            return jsonify({'success': False, 'message': 'PIN já cadastrado.'}), 400
        logger.debug(f"PIN disponível: {pin}")
        logger.debug(f"Tempo de execução /check_pin: {time() - start_time:.3f}s")
        return jsonify({'success': True, 'message': 'PIN disponível.'})
    except Exception as e:
        logger.error(f"Erro inesperado em /check_pin: {str(e)}")
        logger.debug(f"Tempo de execução /check_pin: {time() - start_time:.3f}s")
        return jsonify({'success': False, 'message': 'Erro inesperado ao verificar PIN.'}), 500

# Rota para Verificar Matrícula
@app.route('/check_employer_code', methods=['POST'])
def check_employer_code():
    if 'employee_id' not in session:
        logger.warning("Tentativa de acesso a /check_employer_code sem login.")
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        logger.warning(f"Usuário com role {session['role']} tentou acessar /check_employer_code.")
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

    employer_code = request.json.get('employer_code')
    if not employer_code:
        logger.warning("Matrícula não fornecida na requisição /check_employer_code.")
        return jsonify({'success': False, 'message': 'Matrícula não fornecida.'}), 400

    try:
        existing_employee = Employee.query.filter_by(employer_code=employer_code).first()
        if existing_employee:
            logger.debug(f"Matrícula já cadastrada: {employer_code}")
            return jsonify({'success': False, 'message': 'Matrícula já cadastrada.'}), 400
        logger.debug(f"Matrícula disponível: {employer_code}")
        return jsonify({'success': True, 'message': 'Matrícula disponível.'})
    except OperationalError as e:
        logger.error(f"Erro ao acessar a tabela employee em /check_employer_code: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao verificar matrícula: Tabela de funcionários não está configurada corretamente.'}), 500
    except Exception as e:
        logger.error(f"Erro inesperado em /check_employer_code: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro inesperado ao verificar matrícula.'}), 500

@app.route('/add_unit', methods=['GET', 'POST'])
def add_unit():
    if 'employee_id' not in session:
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    unit_id = request.args.get('unit_id', type=int)
    unit = None
    if unit_id:
        unit = Unit.query.get_or_404(unit_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        icj_contract = request.form.get('icj_contract') or None
        sap_contract = request.form.get('sap_contract') or None
        fiscal = request.form.get('fiscal') or None
        field_fiscal = request.form.get('field_fiscal') or None
        preposto_email = request.form.get('preposto_email') or None
        
        if not name:
            flash('O campo Unidade é obrigatório.', 'error')
            return redirect(url_for('add_unit', unit_id=unit_id) if unit_id else url_for('add_unit'))
        
        try:
            if unit_id and unit:
                # Editar unidade existente
                unit.name = name
                unit.icj_contract = icj_contract
                unit.sap_contract = sap_contract
                unit.fiscal = fiscal
                unit.field_fiscal = field_fiscal
                unit.preposto_email = preposto_email
                db.session.commit()
                flash('Unidade atualizada com sucesso.', 'success')
            else:
                # Criar nova unidade
                new_unit = Unit(
                    name=name,
                    icj_contract=icj_contract,
                    sap_contract=sap_contract,
                    fiscal=fiscal,
                    field_fiscal=field_fiscal,
                    preposto_email=preposto_email
                )
                db.session.add(new_unit)
                db.session.commit()
                flash('Unidade cadastrada com sucesso.', 'success')
            return redirect(url_for('add_unit'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar unidade: {str(e)}', 'error')
            return redirect(url_for('add_unit', unit_id=unit_id) if unit_id else url_for('add_unit'))
    
    # Buscar todas as unidades para exibir na tabela
    units = Unit.query.all()
    return render_template('add_unit.html', employee_name=session['employee_name'], unit=unit, units=units)

# Rota para Listar Unidades
@app.route('/get_units', methods=['GET'])
def get_units():
    if 'employee_id' not in session:
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403
    
    units = Unit.query.all()
    units_data = [{
        'id': unit.id,
        'name': unit.name or 'N/A',
        'icj_contract': unit.icj_contract or 'N/A',
        'sap_contract': unit.sap_contract or 'N/A',
        'fiscal': unit.fiscal or 'N/A',
        'field_fiscal': unit.field_fiscal or 'N/A',
        'preposto_email': unit.preposto_email or 'N/A'
    } for unit in units]
    
    print(f"Unidades retornadas: {units_data}")  # Log para depuração
    return jsonify({
        'success': True,
        'units': units_data
    })

# Rota para Excluir Unidade
@app.route('/delete_unit/<int:unit_id>', methods=['POST'])
def delete_unit(unit_id):
    if 'employee_id' not in session:
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403
    
    try:
        unit = Unit.query.get_or_404(unit_id)
        # Verificar se a unidade tem funcionários associados
        employees = Employee.query.filter_by(unit=unit.name).count()
        if employees > 0:
            return jsonify({
                'success': False,
                'message': 'Não é possível excluir a unidade pois há funcionários associados.'
            }), 400
        
        db.session.delete(unit)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Unidade excluída com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao excluir unidade: {str(e)}'}), 500

@app.route('/units', methods=['GET'])
def units():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] not in ['colaborador', 'empregador']:  # Permitir 'empregador' além de 'colaborador'
        print(f"Erro: acesso não autorizado à página de unidades. Papel atual: {session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando units para employee_id: {session.get('employee_id')}, role: {session.get('role')}")
    units = Unit.query.all()  # Lista todas as unidades cadastradas
    return render_template('units.html', employee_name=session['employee_name'], units=units)

@app.route('/get_signed_reports_by_period', methods=['POST'])
def get_signed_reports_by_period():
    if 'employee_id' not in session:
        logger.error("Erro: employee_id não encontrado na sessão")
        return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
    if session['role'] not in ['colaborador', 'empregador']:
        logger.error(f"Erro: acesso não autorizado à busca de relatórios. Papel atual: {session.get('role')}")
        return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    unit_name = data.get('unit_name')

    if not all([start_date_str, end_date_str, unit_name]):
        logger.error("Erro: datas inicial, final ou unidade não fornecidas")
        return jsonify({'success': False, 'message': 'Datas inicial, final e unidade são obrigatórias.'}), 400

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        br_timezone = ZoneInfo("America/Sao_Paulo")
        two_months_ago = datetime.now(br_timezone) - timedelta(days=60)
    except ValueError:
        logger.error("Erro: formato de data inválido")
        return jsonify({'success': False, 'message': 'Formato de data inválido.'}), 400

    unit = Unit.query.filter_by(name=unit_name).first()
    if not unit:
        logger.error(f"Erro: unidade {unit_name} não encontrada")
        return jsonify({'success': False, 'message': 'Unidade não encontrada.'}), 404

    # Buscar todos os colaboradores da unidade com papel 'colaborador'
    employees = Employee.query.filter_by(unit=unit_name, role='colaborador').all()
    
    # Buscar relatórios no período para a unidade, dos últimos 2 meses
    reports = Report.query.join(Employee).filter(
        Report.created_at.between(start_date, end_date),
        Report.created_at >= two_months_ago,
        Employee.unit == unit_name,
        Employee.role == 'colaborador',
        Report.signature_status == 'Assinado'
    ).all()

    # Mapear relatórios por employee_id
    report_map = {report.employee_id: report for report in reports}

    # Preparar dados dos colaboradores
    employees_data = []
    for employee in employees:
        report = report_map.get(employee.id)
        status = 'Assinado' if report else ('Pendente' if report_map.get(employee.id) else 'Não Enviado')
        employees_data.append({
            'employer_code': employee.employer_code or 'N/A',
            'name': employee.name,
            'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
            'position': employee.position or 'N/A',
            'status': status
        })

    logger.debug(f"Colaboradores filtrados com sucesso para unidade {unit_name}")
    return jsonify({
        'success': True,
        'message': 'Colaboradores filtrados com sucesso.',
        'employees': employees_data
    })

@app.route('/send_reports_to_fiscal', methods=['POST'])
def send_reports_to_fiscal():
    try:
        if 'employee_id' not in session:
            logger.error("Erro: employee_id não encontrado na sessão")
            return jsonify({'success': False, 'message': 'Por favor, faça login.'}), 401
        if session['role'] not in ['colaborador', 'empregador']:
            logger.error(f"Erro: acesso não autorizado ao envio de relatórios. Papel atual: {session.get('role')}")
            return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

        data = request.get_json()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        unit_name = data.get('unit_name')

        if not all([start_date_str, end_date_str, unit_name]):
            logger.error("Erro: datas inicial, final ou unidade não fornecidas")
            return jsonify({'success': False, 'message': 'Datas inicial, final e unidade são obrigatórias.'}), 400

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        br_timezone = ZoneInfo("America/Sao_Paulo")
        two_months_ago = datetime.now(br_timezone) - timedelta(days=60)

        # Buscar unidade
        unit = Unit.query.filter_by(name=unit_name).first()
        if not unit:
            logger.error(f"Erro: unidade {unit_name} não encontrada")
            return jsonify({'success': False, 'message': 'Unidade não encontrada.'}), 404

        # Verificar relatórios assinados no período, dos últimos 2 meses
        employees = Employee.query.filter_by(unit=unit_name, role='colaborador').all()
        reports = Report.query.join(Employee).filter(
            Report.created_at.between(start_date, end_date),
            Report.created_at >= two_months_ago,
            Employee.unit == unit_name,
            Employee.role == 'colaborador',
            Report.signature_status == 'Assinado'
        ).all()

        all_signed = all(report.signature_status == 'Assinado' for report in reports) and len(reports) == len(employees)
        if not all_signed:
            logger.error("Erro: nem todos os relatórios da unidade estão assinados")
            return jsonify({'success': False, 'message': 'Nem todos os relatórios da unidade estão assinados.'}), 400

        # Gerar relatório consolidado em PDF
        filename = secure_filename(f"consolidated_report_{unit_name}_{start_date_str}.pdf")
        file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
        c = canvas.Canvas(file_path, pagesize=A4)
        width, height = A4

        for employee in employees:
            activities = Activity.query.filter_by(employee_id=employee.id).filter(
                Activity.date >= start_date,
                Activity.date <= end_date
            ).all()
            employee_data = {
                'employer_code': employee.employer_code or 'N/A',
                'name': employee.name,
                'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
                'position': employee.position or 'N/A',
                'unit': employee.unit or 'N/A',
                'department': employee.department or 'N/A',
                'phone': employee.phone or 'N/A',
                'activities': [
                    {
                        'date': activity.date.strftime('%d/%m/%Y'),
                        'description': activity.description,
                        'project': activity.project or 'N/A',
                        'location': activity.location or 'N/A',
                        'type': activity.type or 'N/A',
                        'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
                    } for activity in activities
                ]
            }
            c.setFont('Helvetica-Bold', 16)
            c.drawCentredString(width/2, height - 2*cm, f"Relatório Consolidado - {employee_data['name']}")
            c.setFont('Helvetica', 12)
            c.drawString(2*cm, height - 3.5*cm, f"Matrícula: {employee_data['employer_code']}")
            c.drawString(2*cm, height - 4*cm, f"Data de Admissão: {employee_data['admission_date']}")
            c.drawString(2*cm, height - 4.5*cm, f"Função: {employee_data['position']}")
            c.drawString(2*cm, height - 5*cm, f"Unidade: {employee_data['unit']}")
            c.drawString(2*cm, height - 5.5*cm, f"Departamento: {employee_data['department']}")
            c.drawString(2*cm, height - 6*cm, f"Telefone: {employee_data['phone']}")
            c.setFont('Helvetica-Bold', 12)
            c.drawString(2*cm, height - 7.5*cm, "Atividades:")
            c.setFont('Helvetica', 10)
            y = height - 8*cm
            c.drawString(2*cm, y, "Data")
            c.drawString(5*cm, y, "Descrição")
            c.drawString(10*cm, y, "Projeto")
            c.drawString(13*cm, y, "Local")
            c.drawString(15*cm, y, "Tipo")
            c.drawString(17*cm, y, "Horas")
            c.line(2*cm, y-0.2*cm, width-2*cm, y-0.2*cm)
            y -= 0.5*cm
            for activity in employee_data['activities']:
                c.drawString(2*cm, y, activity['date'])
                c.drawString(5*cm, y, activity['description'][:30] + ('...' if len(activity['description']) > 30 else ''))
                c.drawString(10*cm, y, activity['project'])
                c.drawString(13*cm, y, activity['location'])
                c.drawString(15*cm, y, activity['type'])
                c.drawString(17*cm, y, str(activity['hours']))
                y -= 0.5*cm
                if y < 3*cm:
                    c.showPage()
                    c.setFont('Helvetica', 10)
                    y = height - 2*cm
            c.showPage()
        c.save()

        # Enviar e-mail
        fiscal_email = unit.fiscal
        preposto_email = unit.field_fiscal
        msg = Message(
            'Relatórios Assinados - Unidade ' + unit.name,
            sender=app.config['MAIL_USERNAME'],
            recipients=[fiscal_email],
            cc=[preposto_email]
        )
        msg.body = f"Segue anexo os relatórios assinados da unidade {unit.name} para o período {start_date_str} a {end_date_str}."
        with open(file_path, 'rb') as f:
            msg.attach(filename, "application/pdf", f.read())
        mail.send(msg)

        logger.debug(f"Relatórios enviados com sucesso para unidade {unit_name}")
        return jsonify({'success': True, 'message': 'Relatórios enviados com sucesso.'})

    except Exception as e:
        logger.error(f"Erro ao enviar relatórios: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao enviar relatórios: {str(e)}'}), 500 

@app.route('/set_employee_activity', methods=['POST'])
def set_employee_activity():
    if 'employee_id' not in session or session['role'] != 'empregador':
        logger.warning(f"Tentativa de acesso a /set_employee_activity sem permissão: role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    employer_code = request.form.get('employer_code')
    activity_date = request.form.get('activity_date')
    type_ = request.form.get('status')  # Usar 'status' no formulário para compatibilidade
    
    if not all([employer_code, activity_date, type_]):
        logger.warning("Campos obrigatórios não preenchidos em /set_employee_activity")
        flash('Todos os campos são obrigatórios.', 'error')
        return redirect(url_for('home'))
    
    if type_ not in ['Folga', 'Atestado']:
        logger.warning(f"Tipo inválido: {type_}")
        flash('Tipo inválido.', 'error')
        return redirect(url_for('home'))
    
    try:
        activity_date = datetime.strptime(activity_date, '%Y-%m-%d').date()
        if activity_date > date.today():
            logger.warning(f"Data futura não permitida: {activity_date}")
            flash('Não é possível definir atividades para datas futuras.', 'error')
            return redirect(url_for('home'))
        
        employee = Employee.query.filter_by(employer_code=employer_code, role='funcionario').first()
        if not employee:
            logger.warning(f"Funcionário não encontrado: employer_code={employer_code}")
            flash('Funcionário não encontrado.', 'error')
            return redirect(url_for('home'))
        
        activity = Activity.query.filter_by(employee_id=employee.id, date=activity_date).first()
        weekday_map = {
            0: 'Segunda-feira',
            1: 'Terça-feira',
            2: 'Quarta-feira',
            3: 'Quinta-feira',
            4: 'Sexta-feira',
            5: 'Sábado',
            6: 'Domingo'
        }
        weekday = weekday_map[activity_date.weekday()]
        
        if activity:
            activity.type = type_
            activity.description = type_  # Usar o tipo como descrição para Folga/Atestado
            activity.is_edited = True
            activity.weekday = weekday
            activity.project = None
            activity.location = None
            activity.start_datetime = None
            activity.end_datetime = None
        else:
            activity = Activity(
                employee_id=employee.id,
                date=activity_date,
                type=type_,
                description=type_,  # Usar o tipo como descrição
                is_edited=True,
                weekday=weekday,
                project=None,
                location=None,
                start_datetime=None,
                end_datetime=None
            )
            db.session.add(activity)
        
        db.session.commit()
        logger.info(f"Atividade alterada com sucesso: employer_code={employer_code}, date={activity_date}, type={type_}")
        flash(f"Atividade definida como {type_} para {employee.name} em {activity_date.strftime('%d/%m/%Y')}.", 'success')
        return redirect(url_for('home'))
    
    except ValueError:
        logger.warning(f"Formato de data inválido: {activity_date}")
        flash('Formato de data inválido. Use AAAA-MM-DD.', 'error')
        return redirect(url_for('home'))
    except IntegrityError:
        db.session.rollback()
        logger.error("Erro de integridade ao salvar atividade")
        flash('Erro ao salvar atividade. Tente novamente.', 'error')
        return redirect(url_for('home'))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar atividade: {str(e)}")
        flash(f'Erro ao salvar atividade: {str(e)}', 'error')
        return redirect(url_for('home'))

# Rota para salvar atividade
@app.route('/save_activity', methods=['POST'])
def save_activity():
    if 'employee_id' not in session or session['role'] != 'funcionario':
        logger.warning(f"Tentativa de acesso a /save_activity sem permissão: role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    day = int(request.form.get('day'))
    month = int(request.form.get('month'))
    year = int(request.form.get('year'))
    description = request.form.get('description', '').strip()
    project = request.form.get('project', '').strip() or None
    location = request.form.get('location', '').strip() or None

    if not description:
        logger.warning(f"Descrição vazia para employee_id={session['employee_id']}, date={year}-{month:02d}-{day:02d}")
        flash('A descrição da atividade é obrigatória.', 'error')
        return redirect(url_for('activities', month=month, year=year))

    try:
        activity_date = date(year, month, day)
        if activity_date.weekday() >= 5:
            logger.warning(f"Tentativa de salvar atividade em final de semana: {activity_date}")
            flash('Não é possível salvar atividades em finais de semana.', 'error')
            return redirect(url_for('activities', month=month, year=year))

        # Validar dias anteriores não preenchidos
        today = date.today()
        start_date = date(year, month, 1)
        if activity_date > start_date:
            previous_days = (
                Activity.query
                .filter_by(employee_id=session['employee_id'])
                .filter(
                    Activity.date >= start_date,
                    Activity.date < activity_date,
                    Activity.date <= today,
                    db.func.dayofweek(Activity.date).in_([2, 3, 4, 5, 6])  # Dias úteis (seg-sex)
                )
                .all()
            )
            missing_days = [
                d for d in range(1, activity_date.day)
                if date(year, month, d).weekday() < 5
                and not any(a.date.day == d for a in previous_days)
                and date(year, month, d) <= today
            ]
            if missing_days:
                logger.warning(f"Dias anteriores não preenchidos: {missing_days}")
                flash('Você deve preencher todas as atividades de dias úteis anteriores antes de salvar esta atividade.', 'error')
                return redirect(url_for('activities', month=month, year=year))

        activity = Activity.query.filter_by(employee_id=session['employee_id'], date=activity_date).first()
        weekday_map = {
            0: 'Segunda-feira',
            1: 'Terça-feira',
            2: 'Quarta-feira',
            3: 'Quinta-feira',
            4: 'Sexta-feira',
            5: 'Sábado',
            6: 'Domingo'
        }
        weekday = weekday_map[activity_date.weekday()]

        if activity:
            if activity.is_edited or activity.type in ['Folga', 'Atestado']:
                logger.warning(f"Tentativa de editar atividade bloqueada: employee_id={session['employee_id']}, date={activity_date}")
                flash('Esta atividade não pode ser editada.', 'error')
                return redirect(url_for('activities', month=month, year=year))
            activity.description = description
            activity.project = project
            activity.location = location
            activity.weekday = weekday
            activity.type = None  # Atividades normais não têm tipo específico
        else:
            activity = Activity(
                employee_id=session['employee_id'],
                date=activity_date,
                description=description,
                project=project,
                location=location,
                weekday=weekday,
                type=None,
                is_edited=False,
                start_datetime=None,
                end_datetime=None
            )
            db.session.add(activity)

        db.session.commit()
        logger.info(f"Atividade salva com sucesso: employee_id={session['employee_id']}, date={activity_date}")
        flash('Atividade salva com sucesso.', 'success')
        return redirect(url_for('activities', month=month, year=year))

    except ValueError:
        logger.warning(f"Formato de data inválido: {year}-{month:02d}-{day:02d}")
        flash('Formato de data inválido.', 'error')
        return redirect(url_for('activities', month=month, year=year))
    except IntegrityError:
        db.session.rollback()
        logger.error("Erro de integridade ao salvar atividade")
        flash('Erro ao salvar atividade. Tente novamente.', 'error')
        return redirect(url_for('activities', month=month, year=year))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar atividade: {str(e)}")
        flash(f'Erro ao salvar atividade: {str(e)}', 'error')
        return redirect(url_for('activities', month=month, year=year))

# Rota para atividades
@app.route('/activities', methods=['GET'])
def activities():
    if 'employee_id' not in session:
        logger.warning("Tentativa de acesso a /activities sem login")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))

    if session.get('role') != 'funcionario':
        logger.warning(f"Usuário com role {session.get('role')} tentou acessar /activities")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    logger.info(f"Acessando atividades para employee_id: {session.get('employee_id')}")

    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))

    employee = Employee.query.get(session['employee_id'])
    if not employee:
        logger.error("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('index'))

    logger.info(f"Dados do funcionário: Nome={employee.name}, Unidade={employee.unit}, Função={employee.position}")

    days_in_month = get_days_in_month(year, month)

    activities = (
        Activity.query
        .filter_by(employee_id=session['employee_id'])
        .filter(
            db.extract('month', Activity.date) == month,
            db.extract('year', Activity.date) == year
        )
        .all()
    )
    activities_dict = {
        activity.date.day: {
            'description': activity.description,
            'project': activity.project,
            'location': activity.location,
            'weekday': activity.weekday,
            'start_datetime': activity.start_datetime,
            'end_datetime': activity.end_datetime
        } for activity in activities
    }
    activities_is_edited = {activity.date.day: activity.is_edited for activity in activities}
    status_dict = {
        activity.date.day: activity.type if activity.type in ['Folga', 'Atestado'] else 'Concluído' if activity.description else 'Pendente'
        for activity in activities
    }

    today = datetime.now().date()
    _, last_day = calendar.monthrange(year, month)

    for day in range(1, last_day + 1):
        if day not in status_dict:
            activity_date = date(year, month, day)
            is_weekend = activity_date.weekday() >= 5
            if is_weekend:
                status_dict[day] = None
            elif activity_date > today:
                status_dict[day] = 'Pendente'
            else:
                status_dict[day] = 'Em Falta'

    report_count = Report.query.filter_by(employee_id=employee.id).count()
    report_number = f"#{report_count + 1}"

    total_days = sum(
        1 for d in range(1, last_day + 1)
        if date(year, month, d).weekday() < 5
    )
    completed_days = sum(
        1 for d in range(1, last_day + 1)
        if status_dict.get(d) == 'Concluído' and date(year, month, d).weekday() < 5
    )
    folga_atestado_days = sum(
        1 for d in range(1, last_day + 1)
        if status_dict.get(d) in ['Folga', 'Atestado'] and date(year, month, d).weekday() < 5
    )
    pending_days = sum(
        1 for d in range(today.day + 1, last_day + 1)
        if date(year, month, d).weekday() < 5 and status_dict.get(d) == 'Pendente'
    )
    missing_days = sum(
        1 for d in range(1, min(today.day, last_day) + 1)
        if date(year, month, d).weekday() < 5 and status_dict.get(d) == 'Em Falta'
    )

    return render_template(
        'activities.html',
        employee_name=session['employee_name'],
        department=session.get('department'),
        current_month=month,
        current_year=year,
        days_in_month=days_in_month,
        activities=activities_dict,
        activities_is_edited=activities_is_edited,
        status_dict=status_dict,
        total_days=total_days,
        completed_days=completed_days,
        pending_days=pending_days,
        missing_days=missing_days,
        report_number=report_number,
    )

@app.route('/add_activity', methods=['POST'])
def add_activity():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'colaborador':
        print("Erro: acesso não autorizado para adicionar atividades")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Adicionando atividade para employee_id: {session.get('employee_id')}")
    
    month = int(request.form.get('month', datetime.now().month))
    year = int(request.form.get('year', datetime.now().year))

    try:
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            activity_key = f'activity_{day}'
            description = request.form.get(activity_key)
            if description and description.strip():
                activity_date = date(year, month, day)
                existing_activity = Activity.query.filter_by(
                    employee_id=session['employee_id'],
                    date=activity_date
                ).first()
                if existing_activity:
                    existing_activity.description = description
                    existing_activity.weekday = activity_date.strftime('%A')
                else:
                    new_activity = Activity(
                        employee_id=session['employee_id'],
                        description=description,
                        date=activity_date,
                        weekday=activity_date.strftime('%A')
                    )
                    db.session.add(new_activity)
        db.session.commit()
        flash('Atividades registradas com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao registrar atividades: {str(e)}")
        flash(f'Erro ao registrar atividades: {str(e)}.', 'error')

    return redirect(url_for('activities', month=month, year=year))

@app.route('/add_single_activity', methods=['POST'])
def add_single_activity():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))  # Alterado de 'main.index' para 'index'
    if session['role'] != 'funcionario':
        print("Erro: acesso não autorizado para adicionar atividade")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))  # Alterado de 'main.index' para 'index'
    
    print(f"Adicionando/editando atividade única para employee_id: {session.get('employee_id')}")
    
    day = int(request.form.get('day'))
    month = int(request.form.get('month'))
    year = int(request.form.get('year'))
    description = request.form.get('description')
    action = request.form.get('action')  # 'save' ou 'edit'

    try:
        activity_date = date(year, month, day)
        today = datetime.now().date()

        # Verificar se a data é futura
        if activity_date > today:
            flash('Não é possível salvar atividades para datas futuras.', 'error')
            return redirect(url_for('activities', month=month, year=year))

        # Verificar se todos os dias úteis anteriores no mesmo mês estão preenchidos
        activities = Activity.query.filter_by(employee_id=session['employee_id']).filter(
            db.extract('month', Activity.date) == month,
            db.extract('year', Activity.date) == year
        ).all()
        activities_dict = {activity.date.day: activity.description for activity in activities}
        
        missing_days = []
        for d in range(1, min(day, today.day)):
            check_date = date(year, month, d)
            if check_date.weekday() >= 5:  # Ignorar sábado (5) e domingo (6)
                continue
            if d not in activities_dict or not activities_dict[d].strip():
                missing_days.append(d)
        
        if missing_days:
            flash(f'Você deve preencher as atividades dos dias {", ".join(f"{d:02d}/{month:02d}/{year}" for d in missing_days)} antes de salvar esta atividade.', 'error')
            return redirect(url_for('activities', month=month, year=year))

        # Verificar se a descrição é válida
        if not description or not description.strip():
            flash('A descrição da atividade não pode estar vazia.', 'error')
            return redirect(url_for('activities', month=month, year=year))

        # Buscar atividade existente
        existing_activity = Activity.query.filter_by(
            employee_id=session['employee_id'],
            date=activity_date
        ).first()

        if action == 'edit':
            if not existing_activity:
                flash('Nenhuma atividade encontrada para edição.', 'error')
                return redirect(url_for('activities', month=month, year=year))
            if existing_activity.is_edited:
                flash('Esta atividade já foi editada e não pode ser modificada novamente.', 'error')
                return redirect(url_for('activities', month=month, year=year))
            # Atualizar a atividade
            existing_activity.description = description
            existing_activity.is_edited = True
            existing_activity.weekday = WEEKDAYS_PT[activity_date.weekday()]
            flash(f'Atividade para {activity_date.strftime("%d/%m/%Y")} editada com sucesso!', 'success')
        else:  # action == 'save'
            if existing_activity:
                flash('Atividade já existe para esta data. Use o botão "Editar" para modificá-la.', 'error')
                return redirect(url_for('activities', month=month, year=year))
            # Criar nova atividade
            new_activity = Activity(
                employee_id=session['employee_id'],
                description=description,
                date=activity_date,
                weekday=WEEKDAYS_PT[activity_date.weekday()],
                is_edited=False
            )
            db.session.add(new_activity)
            flash(f'Atividade para {activity_date.strftime("%d/%m/%Y")} salva com sucesso!', 'success')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar/editar atividade única: {str(e)}")
        flash(f'Erro ao salvar/editar atividade: {str(e)}.', 'error')

    return redirect(url_for('activities', month=month, year=year))

@app.route('/generate_report', methods=['GET', 'POST'])
def generate_report():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))

    role = session.get('role')
    employee_id = session.get('employee_id')
    print(f"Acessando generate_report para employee_id: {employee_id}, role: {role}")

    valid_roles = ['colaborador', 'funcionario', 'empregador']
    if not role or role not in valid_roles:
        print(f"Erro: acesso não autorizado para gerar relatório, role recebido: {role}")
        flash(f'Acesso não autorizado. Função inválida ou não fornecida: "{role}". Por favor, faça login novamente.', 'error')
        session.clear()
        return redirect(url_for('index'))

    employee = Employee.query.get(employee_id)
    if not employee:
        print(f"Erro: funcionário não encontrado para employee_id: {employee_id}")
        flash('Funcionário não encontrado.', 'error')
        session.clear()
        return redirect(url_for('index'))

    if role in ['colaborador', 'funcionario']:
        if request.method == 'POST':
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            format_type = request.form.get('format')

            print(f"Recebido: start_date={start_date_str}, end_date={end_date_str}, format={format_type}")

            if not start_date_str or not end_date_str or not format_type:
                print("Erro: Campos do formulário ausentes")
                flash('Todos os campos (data inicial, data final e formato) são obrigatórios.', 'error')
                return redirect(url_for('generate_report'))

            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if start_date > end_date:
                    print("Erro: Data de início posterior à data de fim")
                    flash('Data de início não pode ser posterior à data de fim.', 'error')
                    return redirect(url_for('generate_report'))
            except ValueError as e:
                print(f"Erro de validação de data: {str(e)}")
                flash('Formato de data inválido! Use AAAA-MM-DD.', 'error')
                return redirect(url_for('generate_report'))

            unit = Unit.query.filter_by(name=employee.unit).first()
            fiscal_name = unit.fiscal if unit else 'N/A'
            field_fiscal_name = unit.field_fiscal if unit else 'N/A'
            icj_contract = unit.icj_contract if unit else 'N/A'
            sap_contract = unit.sap_contract if unit else 'N/A'

            current_date = start_date
            all_days = []
            while current_date <= end_date:
                all_days.append(current_date)
                current_date += timedelta(days=1)

            activities = Activity.query.filter_by(employee_id=employee.id).filter(
                Activity.date >= start_date,
                Activity.date <= end_date
            ).all()

            activities_dict = {
                activity.date: {
                    'date': activity.date.strftime('%d/%m/%Y'),
                    'weekday': WEEKDAYS_PT[activity.date.weekday()],
                    'description': activity.description,
                    'project': activity.project or 'N/A',
                    'location': activity.location or 'N/A',
                    'type': activity.type or 'N/A',
                    'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
                } for activity in activities
            }

            report_data = {
                'employer_code': employee.employer_code or 'N/A',
                'name': employee.name,
                'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
                'position': employee.position or 'N/A',
                'unit': employee.unit or 'N/A',
                'department': employee.department or 'N/A',
                'phone': employee.phone or 'N/A',
                'fiscal_name': fiscal_name,
                'field_fiscal_name': field_fiscal_name,
                'icj_contract': icj_contract,
                'sap_contract': sap_contract,
                'client': 'Accerth',
                'manager': 'N/A',
                'activities': []
            }

            for activity_date in all_days:
                if activity_date in activities_dict:
                    report_data['activities'].append(activities_dict[activity_date])
                else:
                    description = 'Não preenchível' if activity_date.weekday() >= 5 else 'Não preenchido'
                    report_data['activities'].append({
                        'date': activity_date.strftime('%d/%m/%Y'),
                        'weekday': WEEKDAYS_PT[activity_date.weekday()],
                        'description': description,
                        'project': 'N/A',
                        'location': 'N/A',
                        'type': 'N/A',
                        'hours': 'N/A'
                    })

            report_count = Report.query.filter_by(employee_id=employee.id).count()
            report_number = f"#{report_count + 1}"
            period = f"{start_date.month:02d}/{start_date.year}"

            os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)

            try:
                if format_type == 'excel':
                    df = pd.DataFrame(report_data['activities'])
                    filename = secure_filename(f"report_{report_number}_{employee.id}.xlsx")
                    file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                    print(f"Gerando Excel em: {file_path}")
                    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                        df.to_excel(writer, sheet_name='Relatório Individual', index=False)
                        worksheet = writer.sheets['Relatório Individual']
                        worksheet.write(0, 0, f"Relatório Individual - {report_data['name']}")
                        worksheet.write(1, 0, f"Matrícula: {report_data['employer_code']}")
                        worksheet.write(2, 0, f"Data de Admissão: {report_data['admission_date']}")
                        worksheet.write(3, 0, f"Função: {report_data['position']}")
                        worksheet.write(4, 0, f"Unidade: {report_data['unit']}")
                        worksheet.write(5, 0, f"Departamento: {report_data['department']}")
                        worksheet.write(6, 0, f"Telefone: {report_data['phone']}")
                    new_report = Report(
                        employee_id=employee.id,
                        report_number=report_number,
                        period=period,
                        format='Excel',
                        file_path=file_path
                    )
                    db.session.add(new_report)
                    db.session.commit()
                    flash('Relatório em Excel gerado com sucesso!', 'success')
                    return send_file(
                        file_path,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True,
                        download_name=filename
                    )

                elif format_type == 'pdf':
                    filename = secure_filename(f"report_{report_number}_{employee.id}.pdf")
                    file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                    print(f"Gerando PDF em: {file_path}")
                    doc = SimpleDocTemplate(file_path, pagesize=A4, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0)
                    width, height = A4
                    elements = []

                    styles = getSampleStyleSheet()
                    title_style = ParagraphStyle(
                        name='Title',
                        fontName='Helvetica-Bold',
                        fontSize=10,
                        textColor=colors.white,
                        alignment=1,
                        spaceAfter=2
                    )
                    normal_style = ParagraphStyle(
                        name='Normal',
                        fontName='Helvetica',
                        fontSize=6,
                        textColor=colors.black,
                        spaceAfter=1,
                        leading=7
                    )
                    italic_style = ParagraphStyle(
                        name='Italic',
                        fontName='Helvetica-Oblique',
                        fontSize=6,
                        textColor=colors.black,
                        spaceAfter=1,
                        leading=7
                    )
                    label_style = ParagraphStyle(
                        name='Label',
                        fontName='Helvetica',
                        fontSize=6,
                        textColor=colors.white,
                        spaceAfter=1,
                        leading=7
                    )
                    bold_style = ParagraphStyle(
                        name='Bold',
                        fontName='Helvetica-Bold',
                        fontSize=7,
                        textColor=colors.white,
                        spaceAfter=2,
                        alignment=1
                    )

                    logo_path = os.path.join('static', 'imagens', 'accerth.logo.jpg')
                    if os.path.exists(logo_path):
                        logo = Image(logo_path, width=3*cm, height=1.5*cm)
                    else:
                        print(f"Erro: Logo não encontrado em {logo_path}")
                        logo = Paragraph("", normal_style)
                    header_data = [
                        [logo, Paragraph("RELATÓRIO DE ATIVIDADE DIÁRIA", title_style), Paragraph(f"Mês de Referência: {period}", title_style)]
                    ]
                    header_table = Table(header_data, colWidths=[3*cm, 9*cm, 9*cm], rowHeights=[1.5*cm])
                    header_table.setStyle(TableStyle([
                        ('BACKGROUND', (1, 0), (-1, -1), colors.black),
                        ('TEXTCOLOR', (1, 0), (-1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                        ('LEFTPADDING', (0, 0), (0, 0), 0),
                        ('LEFTPADDING', (1, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ]))
                    elements.append(header_table)
                    elements.append(Spacer(1, 0.2*cm))

                    left_info = [
                        [Paragraph("<b>NOME:</b>", label_style), Paragraph(report_data['name'][:50] + ('...' if len(report_data['name']) > 50 else ''), normal_style)],
                        [Paragraph("<b>DATA DE ADMISSÃO:</b>", label_style), Paragraph(report_data['admission_date'], normal_style)],
                        [Paragraph("<b>FUNÇÃO:</b>", label_style), Paragraph(report_data['position'][:50] + ('...' if len(report_data['position']) > 50 else ''), normal_style)],
                        [Paragraph("<b>EMPRESA:</b>", label_style), Paragraph(report_data['client'], normal_style)],
                        [Paragraph("<b>CONTRATO ICJ N°:</b>", label_style), Paragraph(report_data['icj_contract'], normal_style)],
                        [Paragraph("<b>CONTRATO SAP N°:</b>", label_style), Paragraph(report_data['sap_contract'], normal_style)],
                    ]
                    right_info = [
                        [Paragraph("<b>N° DO RELATÓRIO:</b>", label_style), Paragraph(report_number, normal_style)],
                        [Paragraph("<b>CLIENTE:</b>", label_style), Paragraph(report_data['client'], normal_style)],
                        [Paragraph("<b>UNIDADE:</b>", label_style), Paragraph(report_data['unit'][:50] + ('...' if len(report_data['unit']) > 50 else ''), normal_style)],
                        [Paragraph("<b>GERENTE:</b>", label_style), Paragraph(report_data['manager'], normal_style)],
                        [Paragraph("<b>FISCAL:</b>", label_style), Paragraph(report_data['fiscal_name'][:50] + ('...' if len(report_data['fiscal_name']) > 50 else ''), normal_style)],
                        [Paragraph("<b>FISCAL DE CAMPO:</b>", label_style), Paragraph(report_data['field_fiscal_name'][:50] + ('...' if len(report_data['field_fiscal_name']) > 50 else ''), normal_style)],
                    ]
                    left_info_table = Table(left_info, colWidths=[5.25*cm, 5.25*cm], rowHeights=[0.6*cm]*6)
                    left_info_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.black),
                        ('BACKGROUND', (1, 0), (1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    right_info_table = Table(right_info, colWidths=[5.25*cm, 5.25*cm], rowHeights=[0.6*cm]*6)
                    right_info_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.black),
                        ('BACKGROUND', (1, 0), (1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    info_table = Table([[left_info_table, right_info_table]], colWidths=[10.5*cm, 10.5*cm])
                    info_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(info_table)
                    elements.append(Spacer(1, 0.2*cm))

                    header_activity = [
                        [Paragraph("DATA", bold_style), Paragraph("RESUMO SOBRE AS ATIVIDADES", bold_style)]
                    ]
                    header_activity_table = Table(header_activity, colWidths=[3*cm, 18*cm], rowHeights=[0.5*cm])
                    header_activity_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.black),
                        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    elements.append(header_activity_table)

                    for activity in report_data['activities']:
                        date_subtable = [
                            [Paragraph(activity['date'], label_style), Paragraph(activity['weekday'], normal_style)]
                        ]
                        activity_subtable = [
                            [Paragraph(activity['description'][:100] + ('...' if len(activity['description']) > 100 else ''), italic_style if activity['description'] == 'Não preenchível' else normal_style)]
                        ]
                        date_table = Table(date_subtable, colWidths=[1.5*cm, 1.5*cm], rowHeights=[0.5*cm])
                        date_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (0, 0), colors.black),
                            ('BACKGROUND', (1, 0), (1, 0), colors.tan),
                            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
                            ('TEXTCOLOR', (1, 0), (1, 0), colors.black),
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 2),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                            ('TOPPADDING', (0, 0), (-1, -1), 1),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ]))
                        activity_table = Table(activity_subtable, colWidths=[18*cm], rowHeights=[0.5*cm])
                        activity_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey if activity['description'] == 'Não preenchível' else colors.white),
                            ('TEXTCOLOR', (0, 0), (0, 0), colors.black),
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 2),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                            ('TOPPADDING', (0, 0), (-1, -1), 1),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ]))
                        combined_table = Table([[date_table, activity_table]], colWidths=[3*cm, 18*cm])
                        combined_table.setStyle(TableStyle([
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                        ]))
                        elements.append(combined_table)

                    current_date = datetime.now().strftime('%d/%m/%Y')
                    signature_data = [
                        [Paragraph(f"Data: {current_date}", normal_style), Paragraph("Assinatura Funcionário:", normal_style)],
                        [Paragraph("Data: __/__/____", normal_style), Paragraph("Assinatura Fiscal:", normal_style)],
                        [Paragraph("Data: __/__/____", normal_style), Paragraph("Assinatura Preposto:", normal_style)]
                    ]
                    signature_table = Table(signature_data, colWidths=[4*cm, 14*cm], rowHeights=[1.0*cm]*3)
                    signature_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    signature_wrapper = Table([[Spacer(1, 0*cm), signature_table]], colWidths=[3*cm, 18*cm])
                    signature_wrapper.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(signature_wrapper)

                    print("Construindo PDF...")
                    doc.build(elements)
                    print("PDF construído com sucesso")

                    new_report = Report(
                        employee_id=employee.id,
                        report_number=report_number,
                        period=period,
                        format='PDF',
                        file_path=file_path
                    )
                    db.session.add(new_report)
                    db.session.commit()
                    flash('Relatório em PDF gerado com sucesso!', 'success')
                    return send_file(
                        file_path,
                        mimetype='application/pdf',
                        as_attachment=True,
                        download_name=filename
                    )

            except Exception as e:
                db.session.rollback()
                print(f"Erro ao gerar relatório: {str(e)}")
                traceback.print_exc()
                flash(f'Erro ao gerar relatório: {str(e)}', 'error')
                return redirect(url_for('generate_report'))

        return render_template('generate_report.html', employee_name=employee.name)

    elif role == 'empregador':
        if request.method == 'POST':
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            format_type = request.form.get('format')

            print(f"Recebido: start_date={start_date_str}, end_date={end_date_str}, format={format_type}")

            if not start_date_str or not end_date_str or not format_type:
                print("Erro: Campos do formulário ausentes")
                flash('Todos os campos (data inicial, data final e formato) são obrigatórios.', 'error')
                return redirect(url_for('generate_report'))

            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if start_date > end_date:
                    print("Erro: Data de início posterior à data de fim")
                    flash('Data de início não pode ser posterior à data de fim.', 'error')
                    return redirect(url_for('generate_report'))
            except ValueError as e:
                print(f"Erro de validação de data: {str(e)}")
                flash('Formato de data inválido! Use AAAA-MM-DD.', 'error')
                return redirect(url_for('generate_report'))

            unit = Unit.query.filter_by(employer_id=employee.id).first()
            if not unit:
                print("Erro: unidade não encontrada para o empregador")
                flash('Unidade não encontrada.', 'error')
                return redirect(url_for('generate_report'))

            employees = Employee.query.filter_by(unit=unit.name).all()
            if not employees:
                print("Erro: nenhum funcionário encontrado na unidade")
                flash('Nenhum funcionário encontrado na unidade.', 'error')
                return redirect(url_for('generate_report'))

            current_date = start_date
            all_days = []
            while current_date <= end_date:
                all_days.append(current_date)
                current_date += timedelta(days=1)

            consolidated_activities = []
            for emp in employees:
                activities = Activity.query.filter_by(employee_id=emp.id).filter(
                    Activity.date >= start_date,
                    Activity.date <= end_date
                ).all()
                activities_dict = {
                    activity.date: {
                        'date': activity.date.strftime('%d/%m/%Y'),
                        'weekday': WEEKDAYS_PT[activity.date.weekday()],
                        'description': activity.description,
                        'project': activity.project or 'N/A',
                        'location': activity.location or 'N/A',
                        'type': activity.type or 'N/A',
                        'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A',
                        'employee_name': emp.name,
                        'employer_code': emp.employer_code
                    } for activity in activities
                }

                for activity_date in all_days:
                    if activity_date in activities_dict:
                        consolidated_activities.append(activities_dict[activity_date])
                    else:
                        description = 'Não preenchível' if activity_date.weekday() >= 5 else 'Não preenchido'
                        consolidated_activities.append({
                            'date': activity_date.strftime('%d/%m/%Y'),
                            'weekday': WEEKDAYS_PT[activity.date.weekday()],
                            'description': description,
                            'project': 'N/A',
                            'location': 'N/A',
                            'type': 'N/A',
                            'hours': 'N/A',
                            'employee_name': emp.name,
                            'employer_code': emp.employer_code
                        })

            report_data = {
                'unit': unit.name,
                'fiscal_name': unit.fiscal if unit else 'N/A',
                'field_fiscal_name': unit.field_fiscal if unit else 'N/A',
                'icj_contract': unit.icj_contract if unit else 'N/A',
                'sap_contract': unit.sap_contract if unit else 'N/A',
                'client': 'Accerth',
                'manager': 'N/A',
                'activities': consolidated_activities
            }

            report_count = Report.query.count()
            report_number = f"#{report_count + 1}"
            period = f"{start_date.month:02d}/{start_date.year}"

            os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)

            try:
                if format_type == 'excel':
                    df = pd.DataFrame(report_data['activities'])
                    filename = secure_filename(f"consolidated_report_{report_number}.xlsx")
                    file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                    print(f"Gerando Excel em: {file_path}")
                    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                        df.to_excel(writer, sheet_name='Relatório Consolidado', index=False)
                        worksheet = writer.sheets['Relatório Consolidado']
                        worksheet.write(0, 0, f"Relatório Consolidado - Unidade: {report_data['unit']}")
                        worksheet.write(1, 0, f"Contrato ICJ: {report_data['icj_contract']}")
                        worksheet.write(2, 0, f"Contrato SAP: {report_data['sap_contract']}")
                        worksheet.write(3, 0, f"Fiscal: {report_data['fiscal_name']}")
                        worksheet.write(4, 0, f"Fiscal de Campo: {report_data['field_fiscal_name']}")
                    new_report = Report(
                        employee_id=employee.id,
                        report_number=report_number,
                        period=period,
                        format='Excel',
                        file_path=file_path
                    )
                    db.session.add(new_report)
                    db.session.commit()
                    flash('Relatório consolidado em Excel gerado com sucesso!', 'success')
                    return send_file(
                        file_path,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True,
                        download_name=filename
                    )

                elif format_type == 'pdf':
                    filename = secure_filename(f"consolidated_report_{report_number}.pdf")
                    file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                    print(f"Gerando PDF em: {file_path}")
                    doc = SimpleDocTemplate(file_path, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1*cm)
                    width, height = A4
                    elements = []

                    styles = getSampleStyleSheet()
                    title_style = ParagraphStyle(
                        name='Title',
                        fontName='Helvetica-Bold',
                        fontSize=10,
                        textColor=colors.white,
                        alignment=1,
                        spaceAfter=2
                    )
                    normal_style = ParagraphStyle(
                        name='Normal',
                        fontName='Helvetica',
                        fontSize=6,
                        textColor=colors.black,
                        spaceAfter=1,
                        leading=7
                    )
                    italic_style = ParagraphStyle(
                        name='Italic',
                        fontName='Helvetica-Oblique',
                        fontSize=6,
                        textColor=colors.black,
                        spaceAfter=1,
                        leading=7
                    )
                    label_style = ParagraphStyle(
                        name='Label',
                        fontName='Helvetica',
                        fontSize=6,
                        textColor=colors.white,
                        spaceAfter=1,
                        leading=7
                    )
                    bold_style = ParagraphStyle(
                        name='Bold',
                        fontName='Helvetica-Bold',
                        fontSize=7,
                        textColor=colors.white,
                        spaceAfter=2,
                        alignment=1
                    )

                    def draw_page_background(canvas, doc):
                        canvas.saveState()
                        canvas.setFillColor(colors.black)
                        canvas.rect(0, 0, width, height, fill=1)
                        canvas.restoreState()

                    logo_path = os.path.join('static', 'imagens', 'accerth.logo.jpg')
                    if os.path.exists(logo_path):
                        logo = Image(logo_path, width=3*cm, height=1.5*cm)
                    else:
                        print(f"Erro: Logo não encontrado em {logo_path}")
                        logo = Paragraph("", normal_style)
                    header_data = [
                        [logo, Paragraph("RELATÓRIO CONSOLIDADO DE ATIVIDADES", title_style), Paragraph(f"Mês de Referência: {period}", title_style)]
                    ]
                    header_table = Table(header_data, colWidths=[3*cm, 7*cm, 7*cm], rowHeights=[1.5*cm])
                    header_table.setStyle(TableStyle([
                        ('BACKGROUND', (1, 0), (-1, -1), colors.black),
                        ('TEXTCOLOR', (1, 0), (-1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                        ('LEFTPADDING', (0, 0), (0, 0), 0),
                        ('LEFTPADDING', (1, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ]))
                    elements.append(header_table)
                    elements.append(Spacer(1, 0.2*cm))

                    info_data = [
                        [Paragraph("<b>UNIDADE:</b>", label_style), Paragraph(report_data['unit'][:50] + ('...' if len(report_data['unit']) > 50 else ''), normal_style)],
                        [Paragraph("<b>CONTRATO ICJ N°:</b>", label_style), Paragraph(report_data['icj_contract'], normal_style)],
                        [Paragraph("<b>CONTRATO SAP N°:</b>", label_style), Paragraph(report_data['sap_contract'], normal_style)],
                        [Paragraph("<b>FISCAL:</b>", label_style), Paragraph(report_data['fiscal_name'][:50] + ('...' if len(report_data['fiscal_name']) > 50 else ''), normal_style)],
                        [Paragraph("<b>FISCAL DE CAMPO:</b>", label_style), Paragraph(report_data['field_fiscal_name'][:50] + ('...' if len(report_data['field_fiscal_name']) > 50 else ''), normal_style)],
                    ]
                    info_table = Table(info_data, colWidths=[4.25*cm, 12.25*cm], rowHeights=[0.6*cm]*5)
                    info_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.black),
                        ('BACKGROUND', (1, 0), (1, -1), colors.lightyellow),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    elements.append(info_table)
                    elements.append(Spacer(1, 0.2*cm))

                    header_activity = [
                        [Paragraph("DATA", bold_style), Paragraph("FUNCIONÁRIO", bold_style), Paragraph("RESUMO DAS ATIVIDADES", bold_style)]
                    ]
                    header_activity_table = Table(header_activity, colWidths=[3*cm, 5*cm, 9*cm], rowHeights=[0.5*cm])
                    header_activity_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.black),
                        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 2),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                    ]))
                    elements.append(header_activity_table)

                    for activity in report_data['activities']:
                        date_subtable = [
                            [Paragraph(activity['date'], label_style), Paragraph(activity['weekday'], normal_style)]
                        ]
                        activity_subtable = [
                            [Paragraph(activity['employee_name'][:50] + ('...' if len(activity['employee_name']) > 50 else ''), normal_style)],
                            [Paragraph(activity['description'][:100] + ('...' if len(activity['description']) > 100 else ''), italic_style if activity['description'] == 'Não preenchível' else normal_style)]
                        ]
                        date_table = Table(date_subtable, colWidths=[1.5*cm, 1.5*cm], rowHeights=[0.5*cm])
                        date_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (0, 0), colors.black),
                            ('BACKGROUND', (1, 0), (1, 0), colors.tan),
                            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
                            ('TEXTCOLOR', (1, 0), (1, 0), colors.black),
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 2),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                            ('TOPPADDING', (0, 0), (-1, -1), 1),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ]))
                        activity_table = Table(activity_subtable, colWidths=[9*cm], rowHeights=[0.6*cm, 0.6*cm])
                        activity_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 2),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                            ('TOPPADDING', (0, 0), (-1, -1), 1),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ]))
                        combined_table = Table([[date_table, activity_table]], colWidths=[3*cm, 9*cm])
                        elements.append(combined_table)

                    print("Construindo PDF...")
                    doc.build(elements, onFirstPage=draw_page_background, onLaterPages=draw_page_background)
                    print("PDF construído com sucesso")

                    new_report = Report(
                        employee_id=employee.id,
                        report_number=report_number,
                        period=period,
                        format='PDF',
                        file_path=file_path
                    )
                    db.session.add(new_report)
                    db.session.commit()
                    flash('Relatório consolidado em PDF gerado com sucesso!', 'success')
                    return send_file(
                        file_path,
                        mimetype='application/pdf',
                        as_attachment=True,
                        download_name=filename
                    )

            except Exception as e:
                db.session.rollback()
                print(f"Erro ao gerar relatório consolidado: {str(e)}")
                traceback.print_exc()
                flash(f'Erro ao gerar relatório consolidado: {str(e)}', 'error')
                return redirect(url_for('generate_report'))

        return render_template('generate_report.html', employee_name=employee.name)

    return render_template('generate_report.html', employee_name=employee.name)

@app.route('/check_pending_activities', methods=['POST'])
def check_pending_activities():
    try:
        if 'employee_id' not in session or session['role'] != 'funcionario':
            return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

        data = request.get_json()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        format_type = data.get('format')  # Captura o formato (excel ou pdf)

        if not start_date_str or not end_date_str or not format_type:
            return jsonify({'success': False, 'message': 'Todos os campos (data inicial, data final e formato) são obrigatórios.'}), 400

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        # Verificar todos os dias úteis no período
        current_date = start_date
        missing_days = []
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Dias úteis (segunda a sexta)
                activity = Activity.query.filter_by(employee_id=session['employee_id'], date=current_date).first()
                if not activity:
                    missing_days.append(current_date.strftime('%d/%m/%Y'))
            current_date += timedelta(days=1)

        if missing_days:
            return jsonify({
                'success': True,
                'has_pending': True,
                'format': format_type,  # Retorna o formato para uso no frontend
                'message': "Identificamos que ainda existem atividades pendentes que não foram preenchidas em todos os dias úteis deste período. Deseja realmente gerar o relatório do RDAT mesmo assim? Caso prossiga, o relatório será gerado de forma incompleta.",
                'missing_days': missing_days
            })
        else:
            return jsonify({
                'success': True,
                'has_pending': False,
                'format': format_type
            })

    except Exception as e:
        print(f"Erro ao verificar atividades pendentes: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao verificar atividades: {str(e)}'}), 500

@app.route('/track_reports', methods=['GET'])
def track_reports():
    if 'employee_id' not in session:
        logger.error("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'funcionario':
        logger.error("Erro: acesso não autorizado para acompanhar relatórios")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    logger.debug(f"Acessando track_reports para employee_id: {session.get('employee_id')}")
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        logger.error("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('index'))

    # Filtrar relatórios dos últimos 2 meses
    br_timezone = ZoneInfo("America/Sao_Paulo")
    two_months_ago = datetime.now(br_timezone) - timedelta(days=60)
    reports = Report.query.filter(
        Report.employee_id == employee.id,
        Report.created_at >= two_months_ago
    ).order_by(Report.created_at.desc()).all()
    
    return render_template('track_reports.html', employee_name=session['employee_name'], reports=reports)

@app.route('/employer_reports', methods=['GET'])
def employer_reports():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado para acompanhar relatórios de empregador")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando employer_reports para employee_id: {session.get('employee_id')}")
    
    reports = db.session.query(Report, Employee).join(Employee, Report.employee_id == Employee.id).order_by(Report.created_at.desc()).all()
    units = sorted(set(employee.unit for employee in Employee.query.all() if employee.unit))
    
    return render_template('employer_reports.html', 
                           employee_name=session['employee_name'], 
                           role=session['role'], 
                           reports=reports,
                           units=units)

@app.route('/download_report/<int:report_id>')
def download_report(report_id):
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    
    print(f"Baixando relatório {report_id} para employee_id: {session.get('employee_id')}")
    
    report = Report.query.get(report_id)
    if not report:
        print("Erro: relatório não encontrado")
        flash('Relatório não encontrado.', 'error')
        return redirect(url_for('track_reports' if session['role'] == 'colaborador' else 'employer_reports'))
    
    if session['role'] == 'colaborador' and report.employee_id != session['employee_id']:
        print("Erro: colaborador tentando acessar relatório de outro funcionário")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('track_reports'))
    
    try:
        return send_file(
            report.file_path,
            mimetype='application/pdf' if report.format == 'PDF' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"report_{report.report_number}.{report.format.lower()}"
        )
    except Exception as e:
        print(f"Erro ao baixar relatório: {str(e)}")
        flash(f'Erro ao baixar relatório: {str(e)}', 'error')
        return redirect(url_for('track_reports' if session['role'] == 'colaborador' else 'employer_reports'))

@app.route('/validate_period', methods=['POST'])
def validate_period():
    if 'employee_id' not in session:
        return jsonify({'status': 'error', 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403
    
    print(f"Validando período para employee_id: {session.get('employee_id')}")
    
    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        if start_date > end_date:
            return jsonify({'status': 'error', 'message': 'Data de início não pode ser posterior à data de fim.'}), 400
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido! Use AAAA-MM-DD.'}), 400

    employees = Employee.query.filter_by(role='colaborador').all()
    summary = []
    
    for employee in employees:
        current_date = start_date
        weekdays = 0
        while current_date <= end_date:
            if current_date.strftime('%A') not in ['Saturday', 'Sunday']:
                weekdays += 1
            current_date += timedelta(days=1)
        
        activities = Activity.query.filter_by(employee_id=employee.id).filter(
            Activity.date >= start_date,
            Activity.date <= end_date
        ).count()
        
        missing_days = weekdays - activities
        
        summary.append(f"Funcionário: {employee.name}, Matrícula: {employee.employer_code or 'N/A'}, "
                       f"Dias Úteis: {weekdays}, Atividades Registradas: {activities}, Dias Faltantes: {missing_days}")
    
    return jsonify({
        'status': 'success',
        'message': 'Validação concluída com sucesso!',
        'summary': '\n'.join(summary)
    })

@app.route('/generate_employer_report', methods=['POST'])
def generate_employer_report():
    if 'employee_id' not in session:
        return jsonify({'status': 'error', 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403
    
    print(f"Gerando relatório consolidado para employee_id: {session.get('employee_id')}")
    
    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    format_type = data.get('format', 'pdf')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        if start_date > end_date:
            return jsonify({'status': 'error', 'message': 'Data de início não pode ser posterior à data de fim.'}), 400
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido! Use AAAA-MM-DD.'}), 400

    employees = Employee.query.filter_by(role='colaborador').all()
    report_data = []

    for employee in employees:
        activities = Activity.query.filter_by(employee_id=employee.id).filter(
            Activity.date >= start_date,
            Activity.date <= end_date
        ).all()
        
        employee_data = {
            'employer_code': employee.employer_code or 'N/A',
            'name': employee.name,
            'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
            'position': employee.position or 'N/A',
            'unit': employee.unit or 'N/A',
            'department': employee.department or 'N/A',
            'phone': employee.phone or 'N/A',
            'activities': [
                {
                    'date': activity.date.strftime('%d/%m/%Y'),
                    'description': activity.description,
                    'project': activity.project or 'N/A',
                    'location': activity.location or 'N/A',
                    'type': activity.type or 'N/A',
                    'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
                } for activity in activities
            ]
        }
        report_data.append(employee_data)

    report_count = Report.query.filter_by(employee_id=session['employee_id']).count()
    report_number = f"#{report_count + 1}"
    period = f"{start_date.month:02d}/{start_date.year}"

    os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)

    try:
        if format_type == 'excel':
            filename = secure_filename(f"consolidated_report_{report_number}.xlsx")
            file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
            with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                for employee_data in report_data:
                    df = pd.DataFrame(employee_data['activities'])
                    sheet_name = f"{employee_data['name'][:30]}"
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    worksheet = writer.sheets[sheet_name]
                    worksheet.write(0, 0, f"Relatório Consolidado - {employee_data['name']}")
                    worksheet.write(1, 0, f"Matrícula: {employee_data['employer_code']}")
                    worksheet.write(2, 0, f"Data de Admissão: {employee_data['admission_date']}")
                    worksheet.write(3, 0, f"Função: {employee_data['position']}")
                    worksheet.write(4, 0, f"Unidade: {employee_data['unit']}")
                    worksheet.write(5, 0, f"Departamento: {employee_data['department']}")
                    worksheet.write(6, 0, f"Telefone: {employee_data['phone']}")
            return send_file(
                file_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        elif format_type == 'pdf':
            filename = secure_filename(f"consolidated_report_{report_number}.pdf")
            file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
            c = canvas.Canvas(file_path, pagesize=A4)
            width, height = A4
            for employee_data in report_data:
                c.setFont('Helvetica-Bold', 16)
                c.drawCentredString(width/2, height - 2*cm, f"Relatório Consolidado - {employee_data['name']}")
                c.setFont('Helvetica', 12)
                c.drawString(2*cm, height - 3.5*cm, f"Matrícula: {employee_data['employer_code']}")
                c.drawString(2*cm, height - 4*cm, f"Data de Admissão: {employee_data['admission_date']}")
                c.drawString(2*cm, height - 4.5*cm, f"Função: {employee_data['position']}")
                c.drawString(2*cm, height - 5*cm, f"Unidade: {employee_data['unit']}")
                c.drawString(2*cm, height - 5.5*cm, f"Departamento: {employee_data['department']}")
                c.drawString(2*cm, height - 6*cm, f"Telefone: {employee_data['phone']}")
                c.setFont('Helvetica-Bold', 12)
                c.drawString(2*cm, height - 7.5*cm, "Atividades:")
                c.setFont('Helvetica', 10)
                y = height - 8*cm
                c.drawString(2*cm, y, "Data")
                c.drawString(5*cm, y, "Descrição")
                c.drawString(10*cm, y, "Projeto")
                c.drawString(13*cm, y, "Local")
                c.drawString(15*cm, y, "Tipo")
                c.drawString(17*cm, y, "Horas")
                c.line(2*cm, y-0.2*cm, width-2*cm, y-0.2*cm)
                y -= 0.5*cm
                for activity in employee_data['activities']:
                    c.drawString(2*cm, y, activity['date'])
                    c.drawString(5*cm, y, activity['description'][:30] + ('...' if len(activity['description']) > 30 else ''))
                    c.drawString(10*cm, y, activity['project'])
                    c.drawString(13*cm, y, activity['location'])
                    c.drawString(15*cm, y, activity['type'])
                    c.drawString(17*cm, y, str(activity['hours']))
                    y -= 0.5*cm
                    if y < 3*cm:
                        c.showPage()
                        c.setFont('Helvetica', 10)
                        y = height - 2*cm
                c.setFont('Helvetica-Bold', 12)
                c.drawString(2*cm, y - 1*cm, "Assinatura")
                c.setFont('Helvetica', 10)
                c.drawString(2*cm, y - 1.5*cm, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
                c.drawString(2*cm, y - 2*cm, "Assinatura: _______________________________")
                c.showPage()
            c.save()
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )

    except Exception as e:
        print(f"Erro ao gerar relatório consolidado: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar relatório: {str(e)}'}), 500

@app.route('/digital_signature', methods=['GET'])
def digital_signature():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'funcionario':
        print("Erro: acesso não autorizado à página de assinatura digital")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando digital_signature para employee_id: {session.get('employee_id')}")
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        print("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('index'))
    
    # Buscar apenas relatórios em PDF
    reports = Report.query.filter_by(employee_id=employee.id, format='PDF').order_by(Report.created_at.desc()).all()
    response = make_response(render_template('digital_signature.html', employee_name=session['employee_name'], reports=reports))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0'
    return response

@app.route('/fiscal_signature', methods=['GET'])
def fiscal_signature():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'fiscal':
        print("Erro: acesso não autorizado à página de assinatura fiscal")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando fiscal_signature para employee_id: {session.get('employee_id')}")

    # Buscar fiscal
    fiscal = Employee.query.get(session['employee_id'])
    if not fiscal:
        print("Erro: Fiscal não encontrado")
        flash('Fiscal não encontrado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao fiscal")
        flash('Nenhuma unidade associada ao fiscal.', 'error')
        return redirect(url_for('index'))

    # Buscar colaboradores da unidade do fiscal
    employees = Employee.query.filter_by(unit=unit, role='colaborador').all()

    # Buscar relatórios em PDF (não assinados) dos colaboradores da unidade
    reports = (
        db.session.query(Report, Employee)
        .join(Employee, Report.employee_id == Employee.id)
        .filter(Employee.unit == unit, Report.format == 'PDF', ~Report.file_path.like('%_signed%'))
        .order_by(Report.created_at.desc())
        .all()
    )

    response = make_response(
        render_template(
            'fiscal_signature.html',
            fiscal_name=session['employee_name'],
            employees=employees,
            reports=reports
        )
    )
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0'
    return response

@app.route('/signed_reports', methods=['GET'])
def signed_reports():
    if 'employee_id' not in session:
        logger.error("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'funcionario':
        logger.error("Erro: acesso não autorizado para relatórios assinados")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    logger.debug(f"Acessando signed_reports para employee_id: {session.get('employee_id')}")
    
    employee = Employee.query.get(session['employee_id'])
    if not employee:
        logger.error("Erro: funcionário não encontrado")
        flash('Funcionário não encontrado.', 'error')
        return redirect(url_for('index'))

    # Filtrar relatórios assinados dos últimos 2 meses
    br_timezone = ZoneInfo("America/Sao_Paulo")
    two_months_ago = datetime.now(br_timezone) - timedelta(days=60)
    signed_reports = Report.query.filter(
        Report.employee_id == employee.id,
        Report.signature_status == 'Assinado',
        Report.created_at >= two_months_ago
    ).order_by(Report.created_at.desc()).all()
    
    return render_template('signed_reports.html', employee_name=session['employee_name'], signed_reports=signed_reports)

@app.route('/fiscal_signed_reports', methods=['GET'])
def fiscal_signed_reports():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'fiscal':
        print("Erro: acesso não autorizado para relatórios assinados pelo fiscal")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando fiscal_signed_reports para employee_id: {session.get('employee_id')}")

    # Buscar relatórios assinados pelo fiscal
    signed_reports = Report.query.filter_by(employee_id=session['employee_id']).filter(Report.file_path.like('%fiscal_signed%')).order_by(Report.created_at.desc()).all()
    return render_template(
        'fiscal_signed_reports.html',
        fiscal_name=session['employee_name'],
        signed_reports=signed_reports
    )

@app.route('/signed_reports_empregador', methods=['GET', 'POST'])
def signed_reports_empregador():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado para relatórios assinados do empregador")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando signed_reports_empregador para employee_id: {session.get('employee_id')}")

    units = sorted(set(unit.name for unit in Unit.query.all() if unit.name))
    reports = []

    if request.method == 'POST':
        unit = request.json.get('unit')
        period = request.json.get('period')
        try:
            # Buscar relatórios assinados com base nos filtros
            query = db.session.query(Report, Employee).join(Employee, Report.employee_id == Employee.id).filter(
                Report.file_path.like('%_signed%'),
                Report.signature_status != None
            )
            if unit:
                query = query.filter(Employee.unit == unit)
            if period:
                query = query.filter(Report.period == period)
            reports = query.order_by(Report.created_at.desc()).all()
            return jsonify({
                'status': 'success',
                'message': 'Relatórios filtrados com sucesso',
                'reports': [
                    {
                        'id': report.id,
                        'report_number': report.report_number,
                        'name': employee.name,
                        'unit': employee.unit or 'N/A',
                        'date': report.created_at.strftime('%d/%m/%Y'),
                        'signature_status': report.signature_status or 'Pendente'
                    } for report, employee in reports
                ]
            })
        except Exception as e:
            print(f"Erro ao filtrar relatórios: {str(e)}")
            return jsonify({'status': 'error', 'message': f'Erro ao filtrar relatórios: {str(e)}'}), 500

    # Para GET, buscar todos os relatórios assinados
    reports = db.session.query(Report, Employee).join(Employee, Report.employee_id == Employee.id).filter(
        Report.file_path.like('%_signed%'),
        Report.signature_status != None
    ).order_by(Report.created_at.desc()).all()

    return render_template(
        'signed_reports_empregador.html',
        employee_name=session['employee_name'],
        role=session['role'],
        units=units,
        reports=reports
    )

@app.route('/download_individual_report', methods=['POST'])
def download_individual_report():
    if 'employee_id' not in session or session['role'] != 'empregador':
        print("Erro: acesso não autorizado para download de relatório individual")
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403

    data = request.get_json()
    report_id = data.get('report_id')
    print(f"Baixando relatório individual {report_id} para employee_id: {session.get('employee_id')}")

    report = Report.query.get(report_id)
    if not report:
        print("Erro: relatório não encontrado")
        return jsonify({'status': 'error', 'message': 'Relatório não encontrado.'}), 404

    try:
        return send_file(
            report.file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"report_{report.report_number}.pdf"
        )
    except Exception as e:
        print(f"Erro ao baixar relatório individual: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao baixar relatório: {str(e)}'}), 500
    
@app.route('/download_batch_report', methods=['POST'])
def download_batch_report():
    if 'employee_id' not in session or session['role'] != 'empregador':
        print("Erro: acesso não autorizado para download de relatório em lote")
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403

    data = request.get_json()
    unit = data.get('unit')
    period = data.get('period')
    print(f"Baixando relatório em lote para employee_id: {session.get('employee_id')}, unit: {unit}, period: {period}")

    try:
        # Buscar relatórios assinados com base nos filtros
        query = db.session.query(Report, Employee).join(Employee, Report.employee_id == Employee.id).filter(
            Report.file_path.like('%_signed%'),
            Report.signature_status != None
        )
        if unit:
            query = query.filter(Employee.unit == unit)
        if period:
            query = query.filter(Report.period == period)
        reports = query.order_by(Report.created_at.desc()).all()

        if not reports:
            print("Erro: nenhum relatório encontrado para os filtros fornecidos")
            return jsonify({'status': 'error', 'message': 'Nenhum relatório encontrado para os filtros fornecidos.'}), 404

        # Criar um PDF combinado
        output_path = os.path.join(app.config['REPORT_FOLDER'], f"batch_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        pdf_writer = PdfWriter()

        for report, _ in reports:
            if os.path.exists(report.file_path):
                pdf_reader = PdfReader(report.file_path)
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)

        # Salvar o PDF combinado
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)

        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"batch_report_{unit or 'all'}_{period or 'all'}.pdf"
        )
    except Exception as e:
        print(f"Erro ao gerar relatório em lote: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar relatório em lote: {str(e)}'}), 500

@app.route('/save_signed_pdf', methods=['POST'])
def save_signed_pdf():
    try:
        # Obter os dados do formulário
        report_path = request.form.get('report_path')
        signature_data = request.form.get('signature_data')
        signature_x = float(request.form.get('signature_x', 0))
        signature_y = float(request.form.get('signature_y', 0))
        signature_width = float(request.form.get('signature_width', 200))
        signature_height = float(request.form.get('signature_height', 60))

        if not report_path or not signature_data:
            return jsonify({'success': False, 'message': 'Caminho do relatório ou assinatura ausente.'})

        # Verificar se o arquivo PDF existe
        if not os.path.exists(report_path):
            return jsonify({'success': False, 'message': 'Arquivo PDF não encontrado.'})

        # Buscar o relatório original no banco
        report = Report.query.filter_by(file_path=report_path, employee_id=session['employee_id']).first()
        if not report:
            return jsonify({'success': False, 'message': 'Relatório não encontrado no banco de dados.'})

        # Decodificar a imagem da assinatura (base64 para imagem)
        signature_data = signature_data.split(',')[1]  # Remover o prefixo 'data:image/png;base64,'
        signature_bytes = base64.b64decode(signature_data)
        signature_image = Image.open(io.BytesIO(signature_bytes))

        # Converter a imagem para RGB se necessário (para evitar erros com PNGs RGBA)
        if signature_image.mode != 'RGB':
            signature_image = signature_image.convert('RGB')

        # Criar um PDF temporário com a imagem da assinatura
        signature_pdf_path = 'temp_signature.pdf'
        signature_image.save(signature_pdf_path, format='PDF')

        # Abrir o PDF original
        pdf_reader = PdfReader(report_path)
        pdf_writer = PdfWriter()

        # Copiar todas as páginas do PDF original
        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

        # Abrir o PDF da assinatura
        signature_pdf = PdfReader(signature_pdf_path)
        signature_page = signature_pdf.pages[0]

        # Mesclar a assinatura na última página do PDF original
        last_page = pdf_writer.pages[-1]
        page_width = float(last_page.mediabox.width)
        page_height = float(last_page.mediabox.height)

        # Inverter a coordenada Y para o sistema de coordenadas do PDF (origem no canto inferior esquerdo)
        pdf_y = page_height - signature_y - signature_height

        # Aplicar a transformação para escalar e posicionar a assinatura na caixinha
        transformation = Transformation().scale(
            sx=signature_width / float(signature_page.mediabox.width),
            sy=signature_height / float(signature_page.mediabox.height)
        ).translate(tx=signature_x, ty=pdf_y)
        signature_page.add_transformation(transformation)

        # Mesclar a página da assinatura na última página
        last_page.merge_page(signature_page)

        # Salvar o PDF resultante
        output_path = os.path.join(app.config['REPORT_FOLDER'], f"signed_{os.path.basename(report_path)}")
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)

        # Remover o PDF temporário
        os.remove(signature_pdf_path)

        # Registrar o relatório assinado no banco
        new_report = Report(
            employee_id=session['employee_id'],
            report_number=report.report_number,  # Manter o mesmo número do relatório original
            period=report.period,
            format='PDF',
            file_path=output_path,
            created_at=datetime.utcnow()
        )
        db.session.add(new_report)
        db.session.commit()

        return jsonify({'success': True, 'message': 'PDF assinado salvo com sucesso!'})

    except Exception as e:
        print(f"Erro ao salvar PDF: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao salvar PDF: {str(e)}'})
    
@app.route('/save_fiscal_signed_pdf', methods=['POST'])
def save_fiscal_signed_pdf():
    try:
        if 'employee_id' not in session or session['role'] != 'fiscal':
            return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

        # Obter os dados do formulário
        report_path = request.form.get('report_path')
        signature_data = request.form.get('signature_data')
        signature_x = float(request.form.get('signature_x', 0))
        signature_y = float(request.form.get('signature_y', 0))
        signature_width = float(request.form.get('signature_width', 200))
        signature_height = float(request.form.get('signature_height', 60))

        if not report_path or not signature_data:
            return jsonify({'success': False, 'message': 'Caminho do relatório ou assinatura ausente.'})

        # Verificar se o arquivo PDF existe
        if not os.path.exists(report_path):
            return jsonify({'success': False, 'message': 'Arquivo PDF não encontrado.'})

        # Buscar o relatório original no banco
        report = (
            db.session.query(Report)
            .join(Employee, Report.employee_id == Employee.id)
            .filter(
                Report.file_path == report_path,
                Employee.unit == session['unit'],
                Employee.role == 'colaborador'
            )
            .first()
        )
        if not report:
            return jsonify({'success': False, 'message': 'Relatório não encontrado ou não pertence à sua unidade.'})

        # Decodificar a imagem da assinatura (base64 para imagem)
        signature_data = signature_data.split(',')[1]  # Remover o prefixo 'data:image/png;base64,'
        signature_bytes = base64.b64decode(signature_data)
        signature_image = Image.open(io.BytesIO(signature_bytes))

        # Converter a imagem para RGB se necessário
        if signature_image.mode != 'RGB':
            signature_image = signature_image.convert('RGB')

        # Criar um PDF temporário com a imagem da assinatura
        signature_pdf_path = 'temp_fiscal_signature.pdf'
        signature_image.save(signature_pdf_path, format='PDF')

        # Abrir o PDF original
        pdf_reader = PdfReader(report_path)
        pdf_writer = PdfWriter()

        # Copiar todas as páginas do PDF original
        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

        # Abrir o PDF da assinatura
        signature_pdf = PdfReader(signature_pdf_path)
        signature_page = signature_pdf.pages[0]

        # Mesclar a assinatura na última página do PDF original
        last_page = pdf_writer.pages[-1]
        page_width = float(last_page.mediabox.width)
        page_height = float(last_page.mediabox.height)

        # Inverter a coordenada Y para o sistema de coordenadas do PDF
        pdf_y = page_height - signature_y - signature_height

        # Aplicar a transformação para escalar e posicionar a assinatura
        transformation = Transformation().scale(
            sx=signature_width / float(signature_page.mediabox.width),
            sy=signature_height / float(signature_page.mediabox.height)
        ).translate(tx=signature_x, ty=pdf_y)
        signature_page.add_transformation(transformation)

        # Mesclar a página da assinatura na última página
        last_page.merge_page(signature_page)

        # Salvar o PDF resultante
        output_path = os.path.join(app.config['REPORT_FOLDER'], f"fiscal_signed_{os.path.basename(report_path)}")
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)

        # Remover o PDF temporário
        os.remove(signature_pdf_path)

        # Registrar o relatório assinado no banco
        new_report = Report(
            employee_id=session['employee_id'],  # Associar ao fiscal
            report_number=f"{report.report_number}_fiscal",
            period=report.period,
            format='PDF',
            file_path=output_path,
            created_at=datetime.utcnow()
        )
        db.session.add(new_report)
        db.session.commit()

        return jsonify({'success': True, 'message': 'PDF assinado pelo fiscal salvo com sucesso!'})

    except Exception as e:
        print(f"Erro ao salvar PDF assinado pelo fiscal: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao salvar PDF: {str(e)}'})
    
@app.route('/digital_signature_preposto', methods=['GET', 'POST'])
def digital_signature_preposto():
    if 'employee_id' not in session or session['role'] != 'preposto':
        print(f"Sessão inválida: employee_id={session.get('employee_id')}, role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao preposto")
        flash('Nenhuma unidade associada ao preposto.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando digital_signature_preposto para employee_id: {session.get('employee_id')}, unit: {unit}")

    employees = Employee.query.filter_by(unit=unit, role='colaborador').all()
    reports = (
        db.session.query(Report, Employee)
        .join(Employee, Report.employee_id == Employee.id)
        .filter(Employee.unit == unit, Report.format == 'PDF', ~Report.file_path.like('%_signed%'))
        .order_by(Report.created_at.desc())
        .all()
    )

    response = make_response(
        render_template(
            'digital_signature_preposto.html',
            preposto_name=session['employee_name'],
            unit=unit,
            employees=employees,
            reports=reports
        )
    )
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0'
    return response

@app.route('/save_preposto_signed_pdf', methods=['POST'])
def save_preposto_signed_pdf():
    try:
        if 'employee_id' not in session or session['role'] != 'preposto':
            return jsonify({'success': False, 'message': 'Acesso não autorizado.'}), 403

        report_path = request.form.get('report_path')
        signature_data = request.form.get('signature_data')
        signature_x = float(request.form.get('signature_x', 0))
        signature_y = float(request.form.get('signature_y', 0))
        signature_width = float(request.form.get('signature_width', 200))
        signature_height = float(request.form.get('signature_height', 60))

        if not report_path or not signature_data:
            return jsonify({'success': False, 'message': 'Caminho do relatório ou assinatura ausente.'})

        if not os.path.exists(report_path):
            return jsonify({'success': False, 'message': 'Arquivo PDF não encontrado.'})

        report = (
            db.session.query(Report)
            .join(Employee, Report.employee_id == Employee.id)
            .filter(
                Report.file_path == report_path,
                Employee.unit == session['unit'],
                Employee.role == 'colaborador'
            )
            .first()
        )
        if not report:
            return jsonify({'success': False, 'message': 'Relatório não encontrado ou não pertence à sua unidade.'})

        signature_data = signature_data.split(',')[1]
        signature_bytes = base64.b64decode(signature_data)
        signature_image = PILImage.open(io.BytesIO(signature_bytes))

        if signature_image.mode != 'RGB':
            signature_image = signature_image.convert('RGB')

        signature_pdf_path = 'temp_preposto_signature.pdf'
        signature_image.save(signature_pdf_path, format='PDF')

        pdf_reader = PdfReader(report_path)
        pdf_writer = PdfWriter()

        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

        signature_pdf = PdfReader(signature_pdf_path)
        signature_page = signature_pdf.pages[0]

        last_page = pdf_writer.pages[-1]
        page_width = float(last_page.mediabox.width)
        page_height = float(last_page.mediabox.height)

        pdf_y = page_height - signature_y - signature_height

        transformation = Transformation().scale(
            sx=signature_width / float(signature_page.mediabox.width),
            sy=signature_height / float(signature_page.mediabox.height)
        ).translate(tx=signature_x, ty=pdf_y)
        signature_page.add_transformation(transformation)

        last_page.merge_page(signature_page)

        output_path = os.path.join(app.config['REPORT_FOLDER'], f"preposto_signed_{os.path.basename(report_path)}")
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)

        os.remove(signature_pdf_path)

        new_report = Report(
            employee_id=session['employee_id'],
            report_number=f"{report.report_number}_preposto",
            period=report.period,
            format='PDF',
            file_path=output_path,
            created_at=datetime.utcnow(),
            signature_status='Assinado por Preposto'
        )
        db.session.add(new_report)
        db.session.commit()

        return jsonify({'success': True, 'message': 'PDF assinado pelo preposto salvo com sucesso!'})

    except Exception as e:
        print(f"Erro ao salvar PDF assinado pelo preposto: {str(e)}")
        return jsonify({'success': False, 'message': f'Erro ao salvar PDF: {str(e)}'})

@app.route('/sobre')
def sobre():
    return "Página Sobre - Em construção"

@app.route('/faq')
def faq():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'funcionario':
        print("Erro: acesso não autorizado à página de FAQ")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando FAQ para employee_id: {session.get('employee_id')}")
    return render_template('faq.html', employee_name=session['employee_name'])

@app.route('/duvidas')
def duvidas():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado à página de Dúvidas")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))
    
    print(f"Acessando Dúvidas para employee_id: {session.get('employee_id')}")
    return render_template('duvidas.html', employee_name=session['employee_name'])

@app.route('/system_users', methods=['GET'])
def system_users():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'empregador':
        print("Erro: acesso não autorizado à página de usuários do sistema")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando system_users para employee_id: {session.get('employee_id')}")
    
    employers = Employee.query.filter_by(role='empregador').all()
    fiscals = Employee.query.filter_by(role='fiscal').all()
    prepostos = Employee.query.filter_by(role='preposto').all()
    units = Unit.query.all()
    
    return render_template('system_users.html', 
                           employee_name=session['employee_name'], 
                           role=session['role'], 
                           employers=employers, 
                           fiscals=fiscals,
                           prepostos=prepostos, 
                           units=units)

@app.route('/add_system_user', methods=['POST'])
def add_system_user():
    if 'employee_id' not in session or session['role'] != 'empregador':
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403

    name = request.form.get('name')
    email = request.form.get('email')
    role = request.form.get('role')
    unit = request.form.get('unit')
    pin = request.form.get('pin')

    if not all([name, email, role, pin]):
        return jsonify({'status': 'error', 'message': 'Todos os campos (nome, email, papel e PIN) são obrigatórios.'}), 400

    if role not in ['empregador', 'fiscal', 'preposto']:
        return jsonify({'status': 'error', 'message': 'Papel inválido. Use empregador, fiscal ou preposto.'}), 400

    if role == 'preposto' and not unit:
        return jsonify({'status': 'error', 'message': 'Unidade é obrigatória para o papel preposto.'}), 400

    # Verificar unicidade do email apenas para o mesmo papel
    existing_employee = Employee.query.filter_by(email=email, role=role).first()
    if existing_employee:
        return jsonify({'status': 'error', 'message': f'E-mail já cadastrado para o papel {role}.'}), 400

    try:
        employee = Employee(
            name=name,
            email=email,
            pin=generate_password_hash(pin, method='pbkdf2:sha256', salt_length=8),
            role=role,
            unit=unit if role in ['fiscal', 'preposto'] else None,
            photo_url=None
        )
        db.session.add(employee)
        db.session.commit()
        print(f"Usuário do sistema cadastrado: Nome={name}, Email={email}, Papel={role}, Unidade={unit}")
        return jsonify({
            'status': 'success',
            'message': 'Usuário cadastrado com sucesso!',
            'user': {
                'id': employee.id,
                'name': employee.name,
                'email': employee.email,
                'role': employee.role,
                'unit': employee.unit or ''
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao cadastrar usuário do sistema: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao cadastrar usuário: {str(e)}'}), 500

@app.route('/edit_system_user', methods=['POST'])
def edit_system_user():
    if 'employee_id' not in session:
        return jsonify({'status': 'error', 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403

    user_id = request.form.get('user_id')
    name = request.form.get('name')
    email = request.form.get('email')
    pin = request.form.get('pin')
    role = request.form.get('role')
    unit = request.form.get('unit') if role in ['fiscal', 'preposto'] else None

    if not all([user_id, name, email, role]) or (role in ['fiscal', 'preposto'] and not unit):
        return jsonify({'status': 'error', 'message': 'Todos os campos obrigatórios devem ser preenchidos!'}), 400

    user = Employee.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Usuário não encontrado!'}), 404

    existing_user = Employee.query.filter(Employee.email == email, Employee.id != user_id).first()
    if existing_user:
        return jsonify({'status': 'error', 'message': 'E-mail já cadastrado para outro usuário!'}), 400

    if role in ['fiscal', 'preposto'] and not Unit.query.filter_by(name=unit).first():
        return jsonify({'status': 'error', 'message': 'Unidade inválida!'}), 400

    try:
        user.name = name
        user.email = email
        if pin and pin.strip():
            user.pin = generate_password_hash(pin, method='pbkdf2:sha256', salt_length=8)
        user.role = role
        user.unit = unit
        db.session.commit()
        print(f"Usuário atualizado: ID={user_id}, Nome={name}, E-mail={email}, Role={role}, Unidade={unit}")
        return jsonify({
            'status': 'success',
            'message': f'{role.capitalize()} atualizado com sucesso!',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'unit': user.unit or ''
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar usuário: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao atualizar usuário: {str(e)}'}), 500

@app.route('/delete_system_user', methods=['POST'])
def delete_system_user():
    if 'employee_id' not in session:
        return jsonify({'status': 'error', 'message': 'Por favor, faça login.'}), 401
    if session['role'] != 'empregador':
        return jsonify({'status': 'error', 'message': 'Acesso não autorizado.'}), 403

    data = request.get_json()
    user_id = data.get('user_id')
    role = data.get('role')

    user = Employee.query.get(user_id)
    if not user or user.role != role:
        return jsonify({'status': 'error', 'message': 'Usuário não encontrado ou tipo inválido.'}), 404

    if user.id == session['employee_id']:
        return jsonify({'status': 'error', 'message': 'Você não pode excluir sua própria conta!'}), 403

    try:
        db.session.delete(user)
        db.session.commit()
        print(f"Usuário excluído: ID={user_id}, Role={role}")
        return jsonify({'status': 'success', 'message': f'{role.capitalize()} excluído com sucesso!'})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao excluir usuário: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao excluir usuário: {str(e)}'}), 500

@app.route('/home_fiscal', methods=['GET'])
def home_fiscal():
    print("Entrando na rota /home_fiscal")
    if 'employee_id' not in session or session['role'] != 'fiscal':
        print(f"Sessão inválida: employee_id={session.get('employee_id')}, role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao fiscal")
        flash('Nenhuma unidade associada ao fiscal.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando home_fiscal para employee_id: {session.get('employee_id')}, unit: {unit}")

    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))
    employee_id = request.args.get('employee_id', '').strip()
    print(f"Mês: {month}, Ano: {year}, Filtro por employee_id: {employee_id}")

    days_in_month = get_days_in_month(year, month)
    _, last_day = calendar.monthrange(year, month)
    today = datetime.now().date()

    # Buscar fiscal
    fiscal = Employee.query.get(session['employee_id'])
    if not fiscal:
        print("Erro: Fiscal não encontrado")
        flash('Fiscal não encontrado.', 'error')
        return redirect(url_for('index'))

    print(f"Fiscal: {fiscal.name}, Unidade: {fiscal.unit}")

    # Buscar todos os colaboradores da unidade para o filtro
    employees = Employee.query.filter_by(unit=fiscal.unit, role='colaborador').all()
    print(f"Colaboradores encontrados: {len(employees)}")

    # Filtrar colaboradores com base no employee_id, se fornecido
    if employee_id:
        employees_filtered = Employee.query.filter_by(id=employee_id, unit=fiscal.unit, role='colaborador').all()
        if not employees_filtered:
            print(f"Erro: Funcionário com ID {employee_id} não encontrado ou não pertence à unidade")
            flash('Funcionário selecionado inválido ou não pertence à unidade.', 'error')
            employee_id = ''  # Resetar filtro se inválido
            employees_filtered = employees
    else:
        employees_filtered = employees

    # Dicionário para armazenar dados por colaborador
    employee_data = {}
    for employee in employees_filtered:
        print(f"Processando colaborador: {employee.name}")
        # Buscar atividades do colaborador para o mês e ano
        activities = Activity.query.filter_by(employee_id=employee.id).filter(
            db.extract('month', Activity.date) == month,
            db.extract('year', Activity.date) == year
        ).all()
        activities_dict = {
            activity.date.day: {
                'description': activity.description,
                'type': activity.type or 'N/A',
                'project': activity.project or 'N/A',
                'location': activity.location or 'N/A',
                'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
            } for activity in activities
        }

        # Calcular status por dia
        status_dict = {}
        for day in range(1, last_day + 1):
            activity_date = date(year, month, day)
            is_weekend = activity_date.weekday() >= 5  # 5=Sábado, 6=Domingo
            if is_weekend:
                status_dict[day] = None
            elif day in activities_dict:
                status_dict[day] = 'Concluído'
            elif activity_date > today:
                status_dict[day] = 'Pendente'
            else:
                status_dict[day] = 'Em Falta'

        # Calcular estatísticas
        total_days = sum(1 for d in range(1, last_day + 1) if date(year, month, d).weekday() < 5)
        completed_days = len([d for d in range(1, last_day + 1) if date(year, month, d).weekday() < 5 and d in activities_dict])
        pending_days = sum(1 for d in range(today.day + 1, last_day + 1) if date(year, month, d).weekday() < 5 and d not in activities_dict)
        missing_days = sum(1 for d in range(1, min(today.day, last_day) + 1) if date(year, month, d).weekday() < 5 and d not in activities_dict)

        employee_data[employee.id] = {
            'name': employee.name,
            'employer_code': employee.employer_code or 'N/A',
            'position': employee.position or 'N/A',
            'activities_dict': activities_dict,
            'status_dict': status_dict,
            'total_days': total_days,
            'completed_days': completed_days,
            'pending_days': pending_days,
            'missing_days': missing_days
        }

    print(f"Dados de employee_data: {employee_data}")
    return render_template(
        'home_fiscal.html',
        fiscal_name=session['employee_name'],
        unit=unit,
        current_month=month,
        current_year=year,
        days_in_month=days_in_month,
        employee_data=employee_data,
        employees=employees
    )

@app.route('/home_preposto', methods=['GET'])
def home_preposto():
    if 'employee_id' not in session or session['role'] != 'preposto':
        print(f"Sessão inválida: employee_id={session.get('employee_id')}, role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao preposto")
        flash('Nenhuma unidade associada ao preposto.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando home_preposto para employee_id: {session.get('employee_id')}, unit: {unit}")

    # Obter parâmetros de filtro
    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))
    employee_id = request.args.get('employee_id', '').strip()

    # Validar mês e ano
    if month < 1 or month > 12:
        month = datetime.now().month
    if year < 2020 or year > 2025:
        year = datetime.now().year

    # Buscar preposto
    preposto = Employee.query.get(session['employee_id'])
    if not preposto:
        print("Erro: Preposto não encontrado")
        flash('Preposto não encontrado.', 'error')
        return redirect(url_for('index'))

    # Buscar colaboradores da unidade
    employees_query = Employee.query.filter_by(unit=unit, role='colaborador')
    if employee_id:
        employees_query = employees_query.filter_by(id=employee_id)
    employees = employees_query.all()

    if not employees:
        print(f"Nenhum colaborador encontrado para a unidade: {unit}")
        flash('Nenhum colaborador encontrado para a unidade.', 'error')

    # Obter dias do mês
    days_in_month = get_days_in_month(year, month)  # Usar a função auxiliar existente
    _, last_day = monthrange(year, month)
    today = datetime.now().date()

    # Processar dados dos colaboradores
    employee_data = {}
    for employee in employees:
        print(f"Processando colaborador: {employee.name}")
        # Buscar atividades do colaborador para o mês e ano
        activities = Activity.query.filter_by(employee_id=employee.id).filter(
            db.extract('month', Activity.date) == month,
            db.extract('year', Activity.date) == year
        ).all()
        
        # Criar dicionário de atividades
        activities_dict = {
            activity.date.day: {
                'description': activity.description,
                'type': activity.type or 'N/A',
                'project': activity.project or 'N/A',
                'location': activity.location or 'N/A',
                'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
            } for activity in activities
        }

        # Calcular status por dia
        status_dict = {}
        for day in range(1, last_day + 1):
            activity_date = date(year, month, day)
            is_weekend = activity_date.weekday() >= 5  # 5=Sábado, 6=Domingo
            if is_weekend:
                status_dict[day] = None
            elif day in activities_dict:
                status_dict[day] = 'Concluído'
            elif activity_date > today:
                status_dict[day] = 'Pendente'
            else:
                status_dict[day] = 'Em Falta'

        # Calcular estatísticas
        total_days = sum(1 for d in range(1, last_day + 1) if date(year, month, d).weekday() < 5)
        completed_days = len([d for d in range(1, last_day + 1) if date(year, month, d).weekday() < 5 and d in activities_dict])
        pending_days = sum(1 for d in range(today.day + 1, last_day + 1) if date(year, month, d).weekday() < 5 and d not in activities_dict)
        missing_days = sum(1 for d in range(1, min(today.day, last_day) + 1) if date(year, month, d).weekday() < 5 and d not in activities_dict)

        employee_data[employee.id] = {
            'name': employee.name,
            'employer_code': employee.employer_code or 'N/A',
            'position': employee.position or 'N/A',
            'activities_dict': activities_dict,
            'status_dict': status_dict,
            'total_days': total_days,
            'completed_days': completed_days,
            'pending_days': pending_days,
            'missing_days': missing_days
        }

    print(f"Dados de employee_data: {employee_data}")
    return render_template(
        'home_preposto.html',
        preposto_name=session['employee_name'],
        unit=unit,
        employees=employees,
        employee_data=employee_data,
        days_in_month=days_in_month,
        current_month=month,
        current_year=year,
        employee_id=employee_id
    )

@app.route('/generate_report_preposto', methods=['GET', 'POST'])
def generate_report_preposto():
    if 'employee_id' not in session or session['role'] != 'preposto':
        print(f"Sessão inválida: employee_id={session.get('employee_id')}, role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao preposto")
        flash('Nenhuma unidade associada ao preposto.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando generate_report_preposto para employee_id: {session.get('employee_id')}, unit: {unit}")

    employees = Employee.query.filter_by(unit=unit, role='colaborador').all()

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        format_type = request.form.get('format')
        employee_id = request.form.get('employee_id')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                flash('Data de início não pode ser posterior à data de fim.', 'error')
                return redirect(url_for('generate_report_preposto'))
        except ValueError:
            flash('Formato de data inválido! Use AAAA-MM-DD.', 'error')
            return redirect(url_for('generate_report_preposto'))

        if employee_id:
            employees = Employee.query.filter_by(id=employee_id, unit=unit, role='colaborador').all()
            if not employees:
                flash('Funcionário selecionado inválido ou não pertence à unidade.', 'error')
                return redirect(url_for('generate_report_preposto'))

        report_data = []
        for employee in employees:
            activities = Activity.query.filter_by(employee_id=employee.id).filter(
                Activity.date >= start_date,
                Activity.date <= end_date
            ).all()
            employee_data = {
                'employer_code': employee.employer_code or 'N/A',
                'name': employee.name,
                'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
                'position': employee.position or 'N/A',
                'unit': employee.unit or 'N/A',
                'department': employee.department or 'N/A',
                'phone': employee.phone or 'N/A',
                'activities': [
                    {
                        'date': activity.date.strftime('%d/%m/%Y'),
                        'description': activity.description,
                        'project': activity.project or 'N/A',
                        'location': activity.location or 'N/A',
                        'type': activity.type or 'N/A',
                        'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
                    } for activity in activities
                ]
            }
            report_data.append(employee_data)

        report_count = Report.query.filter_by(employee_id=session['employee_id']).count()
        report_number = f"#{report_count + 1}"
        period = f"{start_date.month:02d}/{start_date.year}"

        os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)

        try:
            if format_type == 'excel':
                filename = secure_filename(f"preposto_report_{report_number}.xlsx")
                file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                    for employee_data in report_data:
                        df = pd.DataFrame(employee_data['activities'])
                        sheet_name = f"{employee_data['name'][:30]}"
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        worksheet = writer.sheets[sheet_name]
                        worksheet.write(0, 0, f"Relatório Preposto - {employee_data['name']}")
                        worksheet.write(1, 0, f"Matrícula: {employee_data['employer_code']}")
                        worksheet.write(2, 0, f"Data de Admissão: {employee_data['admission_date']}")
                        worksheet.write(3, 0, f"Função: {employee_data['position']}")
                        worksheet.write(4, 0, f"Unidade: {employee_data['unit']}")
                        worksheet.write(5, 0, f"Departamento: {employee_data['department']}")
                        worksheet.write(6, 0, f"Telefone: {employee_data['phone']}")
                new_report = Report(
                    employee_id=session['employee_id'],
                    report_number=report_number,
                    period=period,
                    format='Excel',
                    file_path=file_path
                )
                db.session.add(new_report)
                db.session.commit()
                flash('Relatório em Excel gerado com sucesso!', 'success')
                return send_file(
                    file_path,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=filename
                )

            elif format_type == 'pdf':
                filename = secure_filename(f"preposto_report_{report_number}.pdf")
                file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                c = canvas.Canvas(file_path, pagesize=A4)
                width, height = A4
                for employee_data in report_data:
                    c.setFont('Helvetica-Bold', 16)
                    c.drawCentredString(width/2, height - 2*cm, f"Relatório Preposto - {employee_data['name']}")
                    c.setFont('Helvetica', 12)
                    c.drawString(2*cm, height - 3.5*cm, f"Matrícula: {employee_data['employer_code']}")
                    c.drawString(2*cm, height - 4*cm, f"Data de Admissão: {employee_data['admission_date']}")
                    c.drawString(2*cm, height - 4.5*cm, f"Função: {employee_data['position']}")
                    c.drawString(2*cm, height - 5*cm, f"Unidade: {employee_data['unit']}")
                    c.drawString(2*cm, height - 5.5*cm, f"Departamento: {employee_data['department']}")
                    c.drawString(2*cm, height - 6*cm, f"Telefone: {employee_data['phone']}")
                    c.setFont('Helvetica-Bold', 12)
                    c.drawString(2*cm, height - 7.5*cm, "Atividades:")
                    c.setFont('Helvetica', 10)
                    y = height - 8*cm
                    c.drawString(2*cm, y, "Data")
                    c.drawString(5*cm, y, "Descrição")
                    c.drawString(10*cm, y, "Projeto")
                    c.drawString(13*cm, y, "Local")
                    c.drawString(15*cm, y, "Tipo")
                    c.drawString(17*cm, y, "Horas")
                    c.line(2*cm, y-0.2*cm, width-2*cm, y-0.2*cm)
                    y -= 0.5*cm
                    for activity in employee_data['activities']:
                        c.drawString(2*cm, y, activity['date'])
                        c.drawString(5*cm, y, activity['description'][:30] + ('...' if len(activity['description']) > 30 else ''))
                        c.drawString(10*cm, y, activity['project'])
                        c.drawString(13*cm, y, activity['location'])
                        c.drawString(15*cm, y, activity['type'])
                        c.drawString(17*cm, y, str(activity['hours']))
                        y -= 0.5*cm
                        if y < 3*cm:
                            c.showPage()
                            c.setFont('Helvetica', 10)
                            y = height - 2*cm
                    c.setFont('Helvetica-Bold', 12)
                    c.drawString(2*cm, y - 1*cm, "Assinatura Preposto")
                    c.setFont('Helvetica', 10)
                    c.drawString(2*cm, y - 1.5*cm, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
                    c.drawString(2*cm, y - 2*cm, f"Preposto: {session['employee_name']}")
                    c.showPage()
                c.save()
                new_report = Report(
                    employee_id=session['employee_id'],
                    report_number=report_number,
                    period=period,
                    format='PDF',
                    file_path=file_path
                )
                db.session.add(new_report)
                db.session.commit()
                flash('Relatório em PDF gerado com sucesso!', 'success')
                return send_file(
                    file_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=filename
                )

        except Exception as e:
            db.session.rollback()
            print(f"Erro ao gerar relatório preposto: {str(e)}")
            flash(f'Erro ao gerar relatório: {str(e)}', 'error')
            return redirect(url_for('generate_report_preposto'))

    return render_template('generate_report_preposto.html', preposto_name=session['employee_name'], unit=unit, employees=employees)

@app.route('/signed_reports_preposto', methods=['GET'])
def signed_reports_preposto():
    if 'employee_id' not in session or session['role'] != 'preposto':
        print(f"Sessão inválida: employee_id={session.get('employee_id')}, role={session.get('role')}")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao preposto")
        flash('Nenhuma unidade associada ao preposto.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando signed_reports_preposto para employee_id: {session.get('employee_id')}, unit: {unit}")

    signed_reports = (
        db.session.query(Report, Employee)
        .join(Employee, Report.employee_id == Employee.id)
        .filter(Employee.unit == unit, Report.file_path.like('%_signed%'))
        .order_by(Report.created_at.desc())
        .all()
    )

    return render_template('signed_reports_preposto.html', preposto_name=session['employee_name'], unit=unit, signed_reports=signed_reports)

@app.route('/generate_fiscal_report', methods=['GET', 'POST'])
def generate_fiscal_report():
    if 'employee_id' not in session:
        print("Erro: employee_id não encontrado na sessão")
        flash('Por favor, faça login.', 'error')
        return redirect(url_for('index'))
    if session['role'] != 'fiscal':
        print("Erro: acesso não autorizado para gerar relatório fiscal")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao fiscal")
        flash('Nenhuma unidade associada ao fiscal.', 'error')
        return redirect(url_for('index'))

    print(f"Acessando generate_fiscal_report para employee_id: {session.get('employee_id')}, unit: {unit}")

    # Buscar todos os colaboradores da unidade para o filtro
    employees = Employee.query.filter_by(unit=unit, role='colaborador').all()

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        format_type = request.form.get('format')
        employee_id = request.form.get('employee_id')  # ID do funcionário selecionado (ou vazio para todos)

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                flash('Data de início não pode ser posterior à data de fim.', 'error')
                return redirect(url_for('generate_fiscal_report'))
        except ValueError:
            flash('Formato de data inválido! Use AAAA-MM-DD.', 'error')
            return redirect(url_for('generate_fiscal_report'))

        # Filtrar funcionários com base no employee_id, se fornecido
        if employee_id:
            employees = Employee.query.filter_by(id=employee_id, unit=unit, role='colaborador').all()
            if not employees:
                flash('Funcionário selecionado inválido ou não pertence à unidade.', 'error')
                return redirect(url_for('generate_fiscal_report'))
        else:
            employees = Employee.query.filter_by(unit=unit, role='colaborador').all()

        report_data = []

        for employee in employees:
            activities = Activity.query.filter_by(employee_id=employee.id).filter(
                Activity.date >= start_date,
                Activity.date <= end_date
            ).all()

            employee_data = {
                'employer_code': employee.employer_code or 'N/A',
                'name': employee.name,
                'admission_date': employee.admission_date.strftime('%d/%m/%Y') if employee.admission_date else 'N/A',
                'position': employee.position or 'N/A',
                'unit': employee.unit or 'N/A',
                'department': employee.department or 'N/A',
                'phone': employee.phone or 'N/A',
                'activities': [
                    {
                        'date': activity.date.strftime('%d/%m/%Y'),
                        'description': activity.description,
                        'project': activity.project or 'N/A',
                        'location': activity.location or 'N/A',
                        'type': activity.type or 'N/A',
                        'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
                    } for activity in activities
                ]
            }
            report_data.append(employee_data)

        report_count = Report.query.filter_by(employee_id=fiscal.id).count()
        report_number = f"#{report_count + 1}"
        period = f"{start_date.month:02d}/{start_date.year}"
        fiscal = Employee.query.get(session['employee_id'])

        os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)

        try:
            if format_type == 'excel':
                filename = secure_filename(f"fiscal_report_{report_number}.xlsx")
                file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                    for employee_data in report_data:
                        df = pd.DataFrame(employee_data['activities'])
                        sheet_name = f"{employee_data['name'][:30]}"
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        worksheet = writer.sheets[sheet_name]
                        worksheet.write(0, 0, f"Relatório Fiscal - {employee_data['name']}")
                        worksheet.write(1, 0, f"Matrícula: {employee_data['employer_code']}")
                        worksheet.write(2, 0, f"Data de Admissão: {employee_data['admission_date']}")
                        worksheet.write(3, 0, f"Função: {employee_data['position']}")
                        worksheet.write(4, 0, f"Unidade: {employee_data['unit']}")
                        worksheet.write(5, 0, f"Departamento: {employee_data['department']}")
                        worksheet.write(6, 0, f"Telefone: {employee_data['phone']}")
                new_report = Report(
                    employee_id=fiscal.id,
                    report_number=report_number,
                    period=period,
                    format='Excel',
                    file_path=file_path
                )
                db.session.add(new_report)
                db.session.commit()
                flash('Relatório em Excel gerado com sucesso!', 'success')
                return send_file(
                    file_path,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=filename
                )

            elif format_type == 'pdf':
                filename = secure_filename(f"fiscal_report_{report_number}.pdf")
                file_path = os.path.join(app.config['REPORT_FOLDER'], filename)
                c = canvas.Canvas(file_path, pagesize=A4)
                width, height = A4
                for employee_data in report_data:
                    c.setFont('Helvetica-Bold', 16)
                    c.drawCentredString(width/2, height - 2*cm, f"Relatório Fiscal - {employee_data['name']}")
                    c.setFont('Helvetica', 12)
                    c.drawString(2*cm, height - 3.5*cm, f"Matrícula: {employee_data['employer_code']}")
                    c.drawString(2*cm, height - 4*cm, f"Data de Admissão: {employee_data['admission_date']}")
                    c.drawString(2*cm, height - 4.5*cm, f"Função: {employee_data['position']}")
                    c.drawString(2*cm, height - 5*cm, f"Unidade: {employee_data['unit']}")
                    c.drawString(2*cm, height - 5.5*cm, f"Departamento: {employee_data['department']}")
                    c.drawString(2*cm, height - 6*cm, f"Telefone: {employee_data['phone']}")
                    c.setFont('Helvetica-Bold', 12)
                    c.drawString(2*cm, height - 7.5*cm, "Atividades:")
                    c.setFont('Helvetica', 10)
                    y = height - 8*cm
                    c.drawString(2*cm, y, "Data")
                    c.drawString(5*cm, y, "Descrição")
                    c.drawString(10*cm, y, "Projeto")
                    c.drawString(13*cm, y, "Local")
                    c.drawString(15*cm, y, "Tipo")
                    c.drawString(17*cm, y, "Horas")
                    c.line(2*cm, y-0.2*cm, width-2*cm, y-0.2*cm)
                    y -= 0.5*cm
                    for activity in employee_data['activities']:
                        c.drawString(2*cm, y, activity['date'])
                        c.drawString(5*cm, y, activity['description'][:30] + ('...' if len(activity['description']) > 30 else ''))
                        c.drawString(10*cm, y, activity['project'])
                        c.drawString(13*cm, y, activity['location'])
                        c.drawString(15*cm, y, activity['type'])
                        c.drawString(17*cm, y, str(activity['hours']))
                        y -= 0.5*cm
                        if y < 3*cm:
                            c.showPage()
                            c.setFont('Helvetica', 10)
                            y = height - 2*cm
                    c.setFont('Helvetica-Bold', 12)
                    c.drawString(2*cm, y - 1*cm, "Assinatura Fiscal")
                    c.setFont('Helvetica', 10)
                    c.drawString(2*cm, y - 1.5*cm, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
                    c.drawString(2*cm, y - 2*cm, f"Fiscal: {fiscal.name}")
                    c.showPage()
                c.save()
                new_report = Report(
                    employee_id=fiscal.id,
                    report_number=report_number,
                    period=period,
                    format='PDF',
                    file_path=file_path
                )
                db.session.add(new_report)
                db.session.commit()
                flash('Relatório em PDF gerado com sucesso!', 'success')
                return send_file(
                    file_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=filename
                )

        except Exception as e:
            db.session.rollback()
            print(f"Erro ao gerar relatório fiscal: {str(e)}")
            flash(f'Erro ao gerar relatório: {str(e)}', 'error')
            return redirect(url_for('generate_fiscal_report'))

    return render_template('generate_fiscal_report.html', fiscal_name=session['employee_name'], unit=unit, employees=employees)

@app.route('/home_fiscal/download', methods=['GET'])
def download_activities():
    if 'employee_id' not in session or session['role'] != 'fiscal':
        print("Erro: acesso não autorizado ao download de atividades")
        flash('Acesso não autorizado.', 'error')
        return redirect(url_for('index'))

    unit = session.get('unit')
    if not unit:
        print("Erro: nenhuma unidade associada ao fiscal")
        flash('Nenhuma unidade associada ao fiscal.', 'error')
        return redirect(url_for('index'))

    print(f"Baixando atividades para employee_id: {session.get('employee_id')}, unit: {unit}")

    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))
    name_filter = request.args.get('name', '').strip().lower()

    # Buscar fiscal
    fiscal = Employee.query.get(session['employee_id'])
    if not fiscal:
        print("Erro: Fiscal não encontrado")
        flash('Fiscal não encontrado.', 'error')
        return redirect(url_for('index'))

    # Buscar colaboradores
    employees_query = Employee.query.filter_by(unit=fiscal.unit, role='colaborador')
    if name_filter:
        employees_query = employees_query.filter(Employee.name.ilike(f'%{name_filter}%'))
    employees = employees_query.all()

    # Preparar dados para CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Nome', 'Matrícula', 'Função', 'Dia', 'Dia da Semana', 'Status', 'Descrição', 'Tipo', 'Projeto', 'Local', 'Horas'])
    
    _, last_day = calendar.monthrange(year, month)
    weekdays = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    today = datetime.now().date()

    for employee in employees:
        activities = Activity.query.filter_by(employee_id=employee.id).filter(
            db.extract('month', Activity.date) == month,
            db.extract('year', Activity.date) == year
        ).all()
        activities_dict = {
            activity.date.day: {
                'description': activity.description,
                'type': activity.type or 'N/A',
                'project': activity.project or 'N/A',
                'location': activity.location or 'N/A',
                'hours': ((activity.end_datetime - activity.start_datetime).total_seconds() / 3600) if activity.start_datetime and activity.end_datetime else 'N/A'
            } for activity in activities
        }

        for day in range(1, last_day + 1):
            activity_date = date(year, month, day)
            is_weekend = activity_date.weekday() >= 5
            status = None if is_weekend else (
                'Concluído' if day in activities_dict else (
                    'Pendente' if activity_date > today else 'Em Falta'
                )
            )
            description = activities_dict.get(day, {}).get('description', 'Nenhuma atividade registrada' if not is_weekend else 'Não preenchível')
            activity_type = activities_dict.get(day, {}).get('type', 'N/A')
            project = activities_dict.get(day, {}).get('project', 'N/A')
            location = activities_dict.get(day, {}).get('location', 'N/A')
            hours = activities_dict.get(day, {}).get('hours', 'N/A')

            writer.writerow([
                employee.name,
                employee.employer_code or 'N/A',
                employee.position or 'N/A',
                f'{day:02d}',
                weekdays[activity_date.weekday()],
                status or '-',
                description,
                activity_type,
                project,
                location,
                hours
            ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=atividades_{unit}_{year}{month:02d}.csv'}
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)
        inspector = inspect(db.engine)
        if not any(col['name'] == 'photo_url' for col in inspector.get_columns('employee')):
            print("Aviso: Coluna 'photo_url' não encontrada na tabela 'employee'. Execute 'flask db migrate' e 'flask db upgrade'.")
        if not inspector.has_table('unit'):
            print("Aviso: Tabela 'unit' não encontrada. Execute 'flask db migrate' e 'flask db upgrade'.")
        json_file_path = 'employees.json'
        if os.path.exists(json_file_path):
            import_employees_from_json(json_file_path)
        else:
            print(f"Arquivo JSON não encontrado: {json_file_path}")
        create_employer_accounts()
        init_scheduler(app, db)  # Inicializar o scheduler
    app.run(host='0.0.0.0', port=5000, debug=True)