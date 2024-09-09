import logging
import uuid
from flask_restful import Resource, marshal, reqparse
from werkzeug.exceptions import NotFound,InternalServerError
from controllers.console.setup import setup_required
from fields.dc_batch_hiting_test_fields import batch_hiting_test_filelds
from controllers.kaas_api import api
from libs.login import current_user, kaas_login_required
from services.dataset_service import DatasetService
from services.dc_batch_hiting_test_service import BatchHitingTestService


class RAGBatchHitTestingApi(Resource):
    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        dataset_id = str(dataset_id)
        # user_id = request.headers.get("User_id", default="123")
        try:
            results = BatchHitingTestService.get_hiting_test_results(dataset_id=dataset_id)
            return {"count":len(results),"data":marshal(results,batch_hiting_test_filelds)},200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))

    @setup_required
    @kaas_login_required    
    def delete(self, dataset_id):
        dataset_id = str(dataset_id)

        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        parser = reqparse.RequestParser()
        parser.add_argument("question_ids", type=list, required=True, location="json")
        args = parser.parse_args()
        question_ids = args["question_ids"]
        try:
            BatchHitingTestService.delete_batch_hiting_test_question(question_ids=question_ids,dataset_id=dataset_id)
            return {"message":"success"},200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))

    @setup_required
    @kaas_login_required         
    def post(self,  dataset_id):
        dataset_id = str(dataset_id)
        user_id = current_user.id#  request.headers.get("User_id", default="123")

        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        parser = reqparse.RequestParser()
        parser.add_argument("questions", type=list, location="json")
        parser.add_argument(
            "retrieval_model", type=dict, required=True, location="json"
        )
        parser.add_argument("limit", type=int,required=True, location="json")
        parser.add_argument("start", type=bool, required=True, location="json")
        args = parser.parse_args()
        try:
            param_response,_ = BatchHitingTestService.update_hiting_test_params(dataset_id=dataset_id,params=args["retrieval_model"],user_id=user_id)
            add_count = BatchHitingTestService.add_test_questions(dataset_id=dataset_id,questions=args["questions"],param_id=param_response['id'],user_id=user_id)
            if args["start"]:
                msg,code= BatchHitingTestService.start_hiting_test(dataset_id=dataset_id,param_id=param_response['id'],account_id=user_id, limit=args["limit"])
            else:
                msg = 'Add Questions'
                code = 200
            return {
                "msg":msg,
                "add_count":add_count,
                "param_id":param_response['id']
            },code
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))


class RAGBatchHitTestingBusyApi(Resource):
    @setup_required
    @kaas_login_required    
    def get(self, dataset_id):
        dataset_id = str(dataset_id)
        try:
            return BatchHitingTestService.has_test_task(dataset_id=dataset_id),200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))          


class RAGBatchHitTestingSegmentResultApi(Resource):

    @setup_required
    @kaas_login_required    
    def get(self, dataset_id:uuid,query_id:str):
        dataset_id = str(dataset_id)
        try:
            return BatchHitingTestService.get_segment_results(dataset_id=dataset_id,query_id=query_id),200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))   
               

class RAGBatchHitTestingResultCommentApi(Resource):

    @setup_required
    @kaas_login_required    
    def get(self,  dataset_id:uuid, query_id:uuid, like:str, seg_id:uuid):
        dataset_id = str(dataset_id)
        query_id = str(query_id)
        seg_id = str(seg_id)
        is_like = 0
        if like == "dislike":
            is_like = -1
        elif like == "like":
            is_like = 1
        try:
            return BatchHitingTestService.comment_result(dataset_id=dataset_id,query_id=query_id,is_like=is_like,seg_id=seg_id)
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))
                       
# get：获取批量召回测试结果，post：批量召回测试，delete:删除测试问题
api.add_resource(RAGBatchHitTestingApi, "/datasets/<uuid:dataset_id>/batch-hit-testing")
# 检测是否有测试任务
api.add_resource(RAGBatchHitTestingBusyApi, "/datasets/<uuid:dataset_id>/batch-hit-testing/busy")
# 根据测试问题ID查询匹配的分段信息
api.add_resource(RAGBatchHitTestingSegmentResultApi, "/datasets/<uuid:dataset_id>/batch-hit-testing/result/<string:query_id>")
# 批量召回点赞或踩
api.add_resource(RAGBatchHitTestingResultCommentApi, "/datasets/<uuid:dataset_id>/batch-hit-testing/<uuid:query_id>/<uuid:seg_id>/<string:like>")