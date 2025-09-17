from app import app

with app.app_context():
    try:
        print(app.scheduler.get_jobs())
    except Exception as e:
        print(f"Erro ao verificar jobs do scheduler: {str(e)}")