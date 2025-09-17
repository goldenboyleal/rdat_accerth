import json
from app import app, db, Employee
from werkzeug.security import generate_password_hash

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
    print("Conectado ao banco de dados. Limpando a tabela employee...")
    Employee.query.delete()
    db.session.commit()
    print("Tabela employee limpa.")
    
    inserted = 0
    for emp in employees_data:
        if 'nome' not in emp or 'pin' not in emp:
            print(f"Erro: Registro inválido, faltando 'nome' ou 'pin': {emp}")
            continue
        pin = str(emp['pin']).strip()  # Garante que o PIN é string e sem espaços
        employer_code = f"A{pin}"  # Gera employer_code como A{pin}
        pin_hash = generate_password_hash(pin, method='pbkdf2:sha256', salt_length=8)
        print(f"Processando funcionário: {emp['nome']}, pin: {pin}, employer_code: {employer_code}, hash: {pin_hash}")
        employee = Employee(
            employer_code=employer_code,
            email=emp.get('email'),  # Inclui email, se presente
            pin=pin_hash,
            name=emp['nome'],
            role=emp.get('role', 'colaborador'),  # Usa 'colaborador' como padrão
            department=emp.get('department'),  # Inclui department, se presente
            phone=emp.get('phone')  # Inclui phone, se presente
        )
        db.session.add(employee)
        inserted += 1
    try:
        db.session.commit()
        print(f"{inserted} funcionários inseridos com sucesso!")
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao inserir funcionários: {str(e)}")