from app import app, db, Employee
from werkzeug.security import check_password_hash

def test_pins(employer_code_list, role='colaborador', test_pin_list=None):
    if test_pin_list is None:
        test_pin_list = ['9171', '4922', '1980', '0456']  # PINs reais do employees.json

    with app.app_context():
        for employer_code, pin in zip(employer_code_list, test_pin_list):
            employee = Employee.query.filter_by(employer_code=employer_code, role=role).first()
            if employee:
                print(f"\nFuncionário: {employee.name}, role: {employee.role}, employer_code: {employee.employer_code}")
                print(f"Hash do PIN no banco: {employee.pin}")
                is_valid = check_password_hash(employee.pin, pin)
                if is_valid:
                    print(f"PIN válido para {employee.name}: {pin}")
                else:
                    print(f"PIN inválido para {employee.name}: {pin}")
            else:
                print(f"Nenhum funcionário encontrado com employer_code='{employer_code}' e role='{role}'")

def test_single_employee(name, pin, employer_code, role='colaborador'):
    with app.app_context():
        employee = Employee.query.filter_by(name=name, employer_code=employer_code, role=role).first()
        if employee:
            print(f"\nTestando PIN para {employee.name}, role: {employee.role}, employer_code: {employee.employer_code}")
            print(f"Hash do PIN no banco: {employee.pin}")
            is_valid = check_password_hash(employee.pin, pin)
            if is_valid:
                print(f"PIN válido: {pin}")
            else:
                print(f"PIN inválido: {pin}")
        else:
            print(f"Funcionário '{name}' não encontrado com employer_code='{employer_code}' e role='{role}'")

if __name__ == "__main__":
    # Testar alguns employer_code e PINs
    employer_code_list = ['A9171', 'A4922', 'A1980', 'A0456']
    test_pin_list = ['9171', '4922', '1980', '0456']

    print("Testando PINs para funcionários com employer_code único...")
    test_pins(employer_code_list=employer_code_list, test_pin_list=test_pin_list)

    print("\nTestando PIN específico para Edilton Silva Da Conceição...")
    test_single_employee(name='Edilton Silva Da Conceição', pin='1980', employer_code='A1980')

    print("\nTestando PIN específico para Vania Porto Alexandrino...")
    test_single_employee(name='Vania Porto Alexandrino', pin='0456', employer_code='A0456')