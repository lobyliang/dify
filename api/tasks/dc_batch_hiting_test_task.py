from datetime import datetime, timezone
import logging
import time

import click
from celery import shared_task

from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dc_models import BatchDatasetHitingTestParams
from services.account_service import AccountService
from services.dataset_service import DatasetService

from services.hit_testing_service import HitTestingService


@shared_task(queue='dataset')
def dc_batch_hiting_test_task(param_id:str,dataset_id:str,account_id:str,limit:int):
    from services.dc_batch_hiting_test_service import BatchHitingTestService
    logging.info(click.style('开始进行知识库批量测试: {}'.format(param_id), fg='green'))
    start_at = time.perf_counter()

    indexing_cache_key = 'batch_hiting_test_{}'.format(param_id)
    redis_client.set('batch_hiting_test_{}'.format(dataset_id), param_id)
    try:
        account = AccountService.load_user(account_id)
        if not account:
            logging.error(click.style('账号不存在: {}'.format(account_id), fg='red'))
            return
        test_param = db.session.query(BatchDatasetHitingTestParams).filter(BatchDatasetHitingTestParams.id == param_id).one_or_none()
        param = test_param.params
        # HitTestingService.hit_testing_args_check(param)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            logging.error(click.style('测试知识库不存在: {}'.format(dataset_id), fg='red'))
            return
        test_items = BatchHitingTestService.get_hiting_test_results(dataset_id)
        for test_item in test_items:
            response = HitTestingService.retrieve(dataset=dataset,account=account,query=test_item.question, retrieval_model=param, limit=limit)
            if "records" in response:
                ret = {}
                for record in response["records"]:
                    segment = record["segment"]
                    ret[segment.id] = {} 
                    ret[segment.id]["score"] = record["score"]
                    ret[segment.id]["hit_count"] = segment.hit_count
                    ret[segment.id]["position"] = segment.position
                    ret[segment.id]["like"] = 0
                    ret[segment.id]["total_like"] = 0
                    ret[segment.id]["total_dislike"] = 0
                if test_item.results:
                    ext_results = test_item.results
                    test_item.last_results = ext_results
                test_item.results = ret
                test_item.param_id = param_id
                test_item.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        time.sleep(100.0)
        redis_client.delete('batch_hiting_test_{}'.format(dataset_id))
        redis_client.setex(indexing_cache_key, 600, 'completed')
        end_at = time.perf_counter()
        logging.info(click.style('测试知识库任务: {} latency: {}'.format(param_id, end_at - start_at), fg='green'))
    except Exception as e:
        logging.exception(f"测试知识库任务 failed:{e}")
    finally:
        redis_client.delete('batch_hiting_test_{}'.format(dataset_id))

    # finally:
    #     redis_client.delete(indexing_cache_key)
    