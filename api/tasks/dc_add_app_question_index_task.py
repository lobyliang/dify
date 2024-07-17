import logging
import time

import click
from celery import shared_task

from core.rag.datasource.vdb.dc_vector_factory import DCVector
from core.rag.models.document import Document
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dc_models import AppQuestions


@shared_task(queue='app_question')
def dc_add_app_question_index_task(question_ids: list[str],tenant_id:str,app_id:str):
    documents = []
    logging.info(click.style('开始创建APP问题索引,AppId: {}'.format(app_id), fg='green'))
    start_at = time.perf_counter()

    indexing_cache_key = 'app_question_indexing_{}'.format(app_id)
    try:
        vector = DCVector(tenant_id=tenant_id)
        metadata = {"app_id": app_id,"tenant_id": tenant_id}
        questions = db.session.query(AppQuestions).filter(AppQuestions.id.in_(question_ids)).all()
        for question in questions:
            metadata['doc_id'] = str(question.id)
            documents.append(Document(page_content=question.questions, metadata=metadata))
            question.status = 'completed'
        vector.create(texts=documents)
        db.session.commit()
        redis_client.setex(indexing_cache_key, 600, 'completed')
        end_at = time.perf_counter()
        logging.info(click.style('App问题索引任务: {} latency: {}'.format(app_id, end_at - start_at), fg='green'))
    except Exception as e:
        logging.exception(f"App问题索引任务 failed:{e}")
    # finally:
    #     redis_client.delete(indexing_cache_key)
    