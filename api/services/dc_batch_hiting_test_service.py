
from flask import json
from flask_restful import marshal

from extensions.ext_database import db
from fields import segment_fields
from models.dataset import (
    DocumentSegment,
)
from models.dc_models import BatchDatasetHitingTest, BatchDatasetHitingTestParams
from services.account_service import AccountService
from services.errors.account import NoPermissionError
from tasks.dc_batch_hiting_test_task import dc_batch_hiting_test_task

class BatchHitingTestService:
    @staticmethod
    def add_test_questions(dataset_id: str, questions: list,param_id:str, user_id: str):
        account = AccountService.load_user(user_id)
        if not account:
            raise NoPermissionError()
        ext_questions = db.session.query(BatchDatasetHitingTest).filter(BatchDatasetHitingTest.dataset_id == dataset_id).all() 
        for question in ext_questions:
            query = question.question
            if query in questions:
                questions.remove(query)
        for question in questions:
            db.session.add(BatchDatasetHitingTest(dataset_id=dataset_id, question=question,param_id=param_id,created_by=user_id))
        db.session.commit()
        return len(questions)

    @staticmethod
    def update_hiting_test_params(dataset_id: str, params: dict, user_id: str):
        account = AccountService.load_user(user_id)
        if not account:
            raise NoPermissionError()
        if not params:
            raise ValueError("请填写测试参数")
        if "top_k" not in params:
            raise ValueError("请填写top_k参数")
        if "score_threshold" not in params:
            raise ValueError("请填写score_threshold参数")
        if "score_threshold_enabled" not in params:
            raise ValueError("请填写score_threshold_enabled参数")
        if "reranking_model" not in params:
            raise ValueError("请填写reranking_model参数")
        if "reranking_enable" not in params:
            raise ValueError("请填写reranking_enable参数")
        
        ext_params = db.session.query(BatchDatasetHitingTestParams).filter(BatchDatasetHitingTestParams.dataset_id == dataset_id).order_by(BatchDatasetHitingTestParams.created_at.desc()).first()
        if ext_params:
           param_id = ext_params.id
           ext_params = ext_params.params
           if params['top_k']==ext_params['top_k'] and\
              params['score_threshold']==ext_params['score_threshold'] and\
              params['score_threshold_enabled']==ext_params['score_threshold_enabled'] and\
              params['reranking_model']==ext_params['reranking_model'] and\
              params['reranking_enable']==ext_params['reranking_enable']:
              return {"message":"无更新","id":param_id},0
        newParams = BatchDatasetHitingTestParams(dataset_id=dataset_id, params=params,created_by=user_id)
        db.session.add(newParams)
        db.session.commit()
        return {"message":"更新成功","id":newParams.id},1
    
    @staticmethod
    def get_hiting_test_params(dataset_id: str):
        params = db.session.query(BatchDatasetHitingTestParams).filter(BatchDatasetHitingTestParams.dataset_id == dataset_id).order_by(BatchDatasetHitingTestParams.created_at.desc()).first()
        if params:
            return params.params
        return {}
    
    @staticmethod
    def get_hiting_test_results(dataset_id: str):
        results = db.session.query(BatchDatasetHitingTest).filter(BatchDatasetHitingTest.dataset_id == dataset_id).order_by(BatchDatasetHitingTest.updated_at.desc()).all()
        return results
    
    @staticmethod
    def get_hiting_test_segments(tenant_id: str,seg_ids:list[str],status_list:list[str]=None):
        query = db.session.query(DocumentSegment).filter(DocumentSegment.tenant_id == tenant_id,DocumentSegment.id.in_(seg_ids))
        if status_list:
            query = query.filter(DocumentSegment.status.in_(status_list))
        segments = query.order_by(DocumentSegment.position).all()
        return {'data':marshal(segments, segment_fields)}

    @staticmethod
    def start_hiting_test(dataset_id: str,param_id:str,account_id:str,limit:int):
        dc_batch_hiting_test_task.delay(param_id,dataset_id,account_id,limit)

    @staticmethod
    def comment_result(dataset_id,query_id,is_like:int,seg_id):
        query_item = db.session.query(BatchDatasetHitingTest).filter(BatchDatasetHitingTest.dataset_id==dataset_id,BatchDatasetHitingTest.id==query_id).one_or_none()
        if query_item:
            result_dict = query_item.results
            if seg_id in result_dict:
                if 'like' in result_dict[seg_id]:
                    if is_like == 0:
                        if result_dict[seg_id]["like"] == 1:
                            query_item.like = query_item.like - 1
                        elif result_dict[seg_id]["like"] == -1:
                            query_item.dislike = query_item.dislike - 1
                        result_dict.remove(seg_id)
                    elif is_like == 1:
                        query_item.like = query_item.like + 1
                        result_dict[seg_id]["like"] +=1
                    elif is_like == -1:
                        query_item.dislike = query_item.dislike + 1
                        result_dict[seg_id]["like"] -=1
                else:
                    result_dict[seg_id]["like"] = is_like
                    if is_like == 1:
                        query_item.like = query_item.like + 1
                    elif is_like == -1:
                        query_item.dislike = query_item.dislike + 1
                query_item.results = result_dict
                db.session.bulk_update_mappings(
                    BatchDatasetHitingTest,
                    [
                        {
                            "id": query_id,
                            "like": query_item.like,
                            "dislike": query_item.dislike,
                            "results": query_item.results,
                        }
                    ],)
                db.session.commit()
                return result_dict
        return {}
    
    @staticmethod
    def delete_batch_hiting_test_question(question_ids:list[str],dataset_id:str):
        try:
            questions = db.session.query(BatchDatasetHitingTest).filter(BatchDatasetHitingTest.dataset_id==dataset_id,BatchDatasetHitingTest.id.in_(question_ids)).all()
            for question in questions:
                db.session.delete(question)
                db.session.flush()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e