import logging
import time

import click
from celery import shared_task

from core.rag.datasource.vdb.dc_vector_factory import DCVector
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dc_models import AppQuestions

@shared_task(queue='dataset')
def dc_delete_app_questions_task(tenant_id: str):
    logging.info(click.style('开始删除APP问题索引,tenant_id: {}'.format(tenant_id), fg='green'))
    start_at = time.perf_counter()

    indexing_cache_key = 'app_question_indexing_{}'.format(tenant_id)
    try:
        vector = DCVector(tenant_id=tenant_id)
        
        questions = db.session.query(AppQuestions).filter(AppQuestions.status == 'deleted', AppQuestions.tenant_id == tenant_id).all()
        # ids = [question.id for question in questions]
        for question in questions:
            try:
                vector.delete_by_ids([question.id])
                db.session.query(AppQuestions).filter(AppQuestions.status == 'deleted', AppQuestions.tenant_id == tenant_id,AppQuestions.id== question.id).delete(synchronize_session=False)
                db.session.flush()
            except Exception as e:
                logging.exception(f"App问题:[{question.id}]删除任务 failed:{e}")
        # db.session.query(AppQuestions).filter(AppQuestions.status == 'deleted', AppQuestions.tenant_id == tenant_id,AppQuestions.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        redis_client.setex(indexing_cache_key, 600, 'completed')
        end_at = time.perf_counter()
        logging.info(click.style('App问题删除任务: {} latency: {}'.format(tenant_id, end_at - start_at), fg='green'))
    except Exception as e:
        db.session.rollback()
        logging.exception(f"App问题删除任务 failed:{e}")