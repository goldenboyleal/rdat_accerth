from scheduler import delete_old_reports
from app import app, db

with app.app_context():
    try:
        delete_old_reports(app, db)
        print("Exclusão manual concluída com sucesso.")
    except Exception as e:
        print(f"Erro na exclusão manual: {str(e)}")