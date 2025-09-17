import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from zoneinfo import ZoneInfo
from models import Report  # Importar a classe Report de models.py

# Configuração de logging
logging.basicConfig(level=logging.INFO, filename='scheduler.log', format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def delete_old_reports(app, db):
    try:
        # Data limite: 2 meses atrás, ajustado para fuso horário -03:00
        br_timezone = ZoneInfo("America/Sao_Paulo")
        two_months_ago = datetime.now(br_timezone) - timedelta(days=60)
        logger.info(f"Iniciando exclusão de relatórios anteriores a {two_months_ago}")
        
        # Buscar relatórios antigos
        old_reports = db.session.query(Report).filter(
            Report.created_at < two_months_ago
        ).all()
        
        if not old_reports:
            logger.info("Nenhum relatório antigo encontrado para exclusão.")
            return
        
        for report in old_reports:
            try:
                # Tentar excluir arquivo físico, ignorar se não existir
                if report.file_path:
                    full_path = os.path.join(app.config['REPORT_FOLDER'], os.path.basename(report.file_path))
                    if os.path.exists(full_path):
                        os.remove(full_path)
                        logger.info(f"Arquivo excluído: {full_path} (Relatório ID={report.id})")
                    else:
                        logger.warning(f"Arquivo não encontrado: {full_path} (Relatório ID={report.id})")
                # Excluir registro do banco
                db.session.delete(report)
                logger.info(f"Relatório excluído: ID={report.id}, Número={report.report_number}, Status={report.signature_status or 'N/A'}")
            except Exception as e:
                logger.error(f"Erro ao excluir relatório ID={report.id}: {str(e)}")
                continue  # Continuar com o próximo relatório
        
        # Commit das exclusões
        db.session.commit()
        logger.info(f"Exclusão de relatórios antigos concluída. {len(old_reports)} relatórios removidos.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro na tarefa de exclusão de relatórios: {str(e)}")

def init_scheduler(app, db: SQLAlchemy):
    try:
        scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
        scheduler.add_job(lambda: delete_old_reports(app, db), 'interval', days=1, id='delete_old_reports')
        scheduler.start()
        logger.info("Scheduler iniciado com sucesso.")
        
        # Registrar o scheduler no app para shutdown correto
        with app.app_context():
            app.scheduler = scheduler
    except Exception as e:
        logger.error(f"Erro ao iniciar o scheduler: {str(e)}")