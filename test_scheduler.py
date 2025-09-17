from scheduler import delete_old_reports
from app import app, db

with app.app_context():
    try:
        delete_old_reports(app, db)
        print("Tarefa do scheduler executada manualmente com sucesso.")
    except Exception as e:
        print(f"Erro ao executar tarefa do scheduler: {str(e)}")