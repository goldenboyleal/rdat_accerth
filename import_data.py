import json
from datetime import datetime
from werkzeug.security import generate_password_hash
from app import app, db, Employee  # Importa do app.py

json_file = "employees.json"

try:
    with open(json_file, 'r', encoding='utf-8') as file:
        employees_data = json.load(file)
    print(f"Arquivo {json_file} lido com sucesso. Contém {len(employees_data)} registros.")
except FileNotFoundError:
    print(f"Erro: Arquivo {json_file} não encontrado!")
    exit(1)
except json.JSONDecodeError:
    print(f"Erro: Arquivo {json_file} contém JSON inválido!")
    exit(1)

with app.app_context():
    # Limpar a tabela employee (cuidado: apaga todos os dados)
    db.drop_all()
    db.create_all()
    print("Tabela employee limpa e recriada.")

    inserted = 0
    for emp in employees_data:
        if 'nome' not in emp or 'pin' not in emp:
            print(f"Erro: Registro inválido, faltando 'nome' ou 'pin': {emp}")
            continue
        pin = str(emp['pin']).strip()  # Garante que o PIN é string e sem espaços
        employer_code = emp.get('Matrícula', f"A{pin}")  # Usa Matrícula ou gera um employer_code
        pin_hash = generate_password_hash(pin, method='pbkdf2:sha256', salt_length=8)
        admission_date = None
        if emp.get('Data Admissão'):
            try:
                admission_date = datetime.strptime(emp['Data Admissão'], '%d/%m/%Y').date()
                print(f"Data Admissão convertida: {admission_date} para {emp['nome']}")
            except ValueError as e:
                print(f"Erro ao converter admission_date para {emp['nome']}: {str(e)}")

        employee = Employee(
            employer_code=employer_code,
            pin=pin_hash,
            name=emp['nome'],
            role='colaborador',
            admission_date=admission_date,
            unit=emp.get('Unidade'),
            position=emp.get('Função')
        )
        db.session.add(employee)
        print(f"Colaborador adicionado: Nome={employee.name}, Unidade={employee.unit}, Data Admissão={employee.admission_date}, Função={employee.position}")
        inserted += 1
    db.session.commit()
    print(f"{inserted} funcionários inseridos com sucesso!")