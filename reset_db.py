from app import app, db, Employee, TimeRecord, Activity
from werkzeug.security import generate_password_hash
from datetime import datetime, date
import json
import os

try:
    # Ativar o contexto da aplicação Flask
    with app.app_context():
        # Dropar e recriar todas as tabelas
        with db.session.no_autoflush:
            db.drop_all()
            db.create_all()

        # Caminho para o arquivo employees.json
        json_path = os.path.join(os.path.dirname(__file__), 'employees.json')
        
        # Ler o arquivo employees.json
        try:
            with open(json_path, 'r', encoding='utf-8') as file:
                employees_data = json.load(file)
        except FileNotFoundError:
            raise Exception("Arquivo employees.json não encontrado no diretório do projeto.")
        except json.JSONDecodeError:
            raise Exception("Erro ao decodificar o arquivo employees.json. Verifique o formato JSON.")

        # Adicionar funcionários do JSON
        employees = []
        used_pins = set()  # Para verificar duplicatas de PIN
        for idx, emp_data in enumerate(employees_data):
            if not all(key in emp_data for key in ['nome', 'pin']):
                print(f"Aviso: Dados incompletos para o colaborador {idx + 1}. Ignorando entrada: {emp_data}")
                continue
            
            name = emp_data['nome']
            pin = emp_data['pin']
            
            # Ajustar PIN de Edilton para consistência com logs
            if name == "Edilton Silva Da Conceição":
                pin = "9171"
            
            # Gerar employer_code como A{pin}
            employer_code = f"A{pin}"
            
            # Verificar duplicatas de PIN
            if pin in used_pins:
                print(f"Aviso: PIN {pin} duplicado para {name}. Ignorando colaborador.")
                continue
            used_pins.add(pin)
            
            employees.append(Employee(
                employer_code=employer_code,
                pin=generate_password_hash(pin),
                name=name,
                role='colaborador'
            ))
        
        db.session.add_all(employees)
        db.session.commit()

        # Adicionar registros de ponto para cada funcionário
        records = []
        for idx, employee in enumerate(employees):
            # Definir horários variados para simular realismo
            hour_in = 8 if idx % 3 == 0 else 8 if idx % 3 == 1 else 9
            minute_in = 0 if idx % 2 == 0 else 30
            hour_out = hour_in + 9  # 8h de trabalho + 1h de almoço
            minute_out = minute_in
            records.append(TimeRecord(
                employee_id=employee.id,
                clock_in=datetime(2025, 8, 7, hour_in, minute_in),
                clock_out=datetime(2025, 8, 7, hour_out, minute_out),
                date=date(2025, 8, 7)
            ))
        db.session.add_all(records)
        db.session.commit()

        # Adicionar atividades de teste para cada funcionário
        activities = []
        activity_types = ['Atividades de TI', 'RH/DP', 'SMS', 'FINANCEIRO']
        activity_descriptions = {
            'Atividades de TI': ['Desenvolvimento de software', 'Suporte técnico', 'Manutenção de sistemas'],
            'RH/DP': ['Processamento de folha', 'Recrutamento', 'Treinamento de equipe'],
            'SMS': ['Monitoramento de segurança', 'Inspeção de equipamentos', 'Treinamento de segurança'],
            'FINANCEIRO': ['Análise de relatórios', 'Controle de despesas', 'Planejamento financeiro']
        }
        for idx, employee in enumerate(employees):
            # Definir horários para manhã e tarde
            hour_in = 8 if idx % 3 == 0 else 8 if idx % 3 == 1 else 9
            minute_in = 0 if idx % 2 == 0 else 30
            # Manhã
            activity_type_morning = activity_types[idx % 4]
            activities.append(Activity(
                employee_id=employee.id,
                type=activity_type_morning,
                start_datetime=datetime(2025, 8, 7, hour_in, minute_in),
                end_datetime=datetime(2025, 8, 7, 12, 0),
                description=activity_descriptions[activity_type_morning][idx % 3],
                date=date(2025, 8, 7)
            ))
            # Tarde
            activity_type_afternoon = activity_types[(idx + 1) % 4]
            activities.append(Activity(
                employee_id=employee.id,
                type=activity_type_afternoon,
                start_datetime=datetime(2025, 8, 7, 13, 0),
                end_datetime=datetime(2025, 8, 7, hour_in + 9, minute_in),
                description=activity_descriptions[activity_type_afternoon][(idx + 1) % 3],
                date=date(2025, 8, 7)
            ))
        db.session.add_all(activities)
        db.session.commit()

        print(f"Banco de dados recriado com sucesso! {len(employees)} funcionários adicionados.")
except Exception as e:
    print(f"Erro ao recriar o banco: {e}")