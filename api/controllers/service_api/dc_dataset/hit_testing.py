import logging
import uuid

from flask import request
from flask_login import current_user
from flask_restful import marshal, reqparse
from httpx import delete
from werkzeug.exceptions import InternalServerError, NotFound
from extensions.ext_database import db
from controllers.service_api.wraps import DatasetApiResource
from models.model import EndUser
from fields.dc_batch_hiting_test_fields import batch_hiting_test_filelds
import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.service_api.dataset.error import DatasetNotInitializedError
from core.errors.error import (
    LLMBadRequestError,
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.model_runtime.errors.invoke import InvokeError
from fields.hit_testing_fields import hit_testing_record_fields
from services.dataset_service import DatasetService
from services.dc_batch_hiting_test_service import BatchHitingTestService
from services.hit_testing_service import HitTestingService


class RAGHitTestingApi(DatasetApiResource):

    def post(self, tenant_id, dataset_id):
        dataset_id_str = str(dataset_id)
        user_id = request.headers.get("User_id", default="123")
        user = request.headers.get("User", default="123")
        end_user = (
            db.session.query(EndUser)
            .filter(
                EndUser.tenant_id == tenant_id,
                EndUser.external_user_id == user_id,
                EndUser.session_id == user,
                EndUser.type == "service_api",
            )
            .first()
        )

        if end_user is None:
            end_user = EndUser(
                tenant_id=tenant_id,
                type="service_api",
                is_anonymous=False,
                name=user,
                external_user_id=user_id,
                session_id=user,
            )
            db.session.add(end_user)
            db.session.commit()
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")

        # try:
        #     DatasetService.check_dataset_permission(dataset, current_user)
        # except services.errors.account.NoPermissionError as e:
        #     raise Forbidden(str(e))

        parser = reqparse.RequestParser()
        parser.add_argument("query", type=str, location="json")
        parser.add_argument(
            "retrieval_model", type=dict, required=False, location="json"
        )
        args = parser.parse_args()

        HitTestingService.hit_testing_args_check(args)

        try:
            response = HitTestingService.retrieve_by_endUser(
                dataset=dataset,
                query=args["query"],
                endUser=end_user,
                retrieval_model=args["retrieval_model"],
                limit=10,
            )

            return {
                "query": response["query"],
                "records": marshal(response["records"], hit_testing_record_fields),
            }
        except services.errors.index.IndexNotInitializedError:
            raise DatasetNotInitializedError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except LLMBadRequestError:
            raise ProviderNotInitializeError(
                "No Embedding Model or Reranking Model available. Please configure a valid provider "
                "in the Settings -> Model Provider."
            )
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            logging.exception("Hit testing failed.")
            raise InternalServerError(str(e))

class RAGBatchHitTestingParamApi(DatasetApiResource):
    def post(self, tenant_id, dataset_id):
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
        
class RAGBatchHitTestingResultApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id):
        dataset_id = str(dataset_id)
        # user_id = request.headers.get("User_id", default="123")
        try:
            results = BatchHitingTestService.get_hiting_test_results(dataset_id=dataset_id)
            return {"count":len(results),"data":marshal(results,batch_hiting_test_filelds)},200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))
    
    def delete(self, tenant_id, dataset_id):
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
        
class RAGBatchHitTestingResultCommentApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id:uuid, query_id:uuid, like:str, seg_id:uuid):
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
    
class RAGBatchHitTestingBusyApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id):
        dataset_id = str(dataset_id)
        try:
            return BatchHitingTestService.has_test_task(dataset_id=dataset_id),200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))

class RAGBatchHitTestingSegmentResultApi(DatasetApiResource):
    def get(self, tenant_id, dataset_id:uuid,query_id:str):
        dataset_id = str(dataset_id)
        try:
            return BatchHitingTestService.get_segment_results(dataset_id=dataset_id,query_id=query_id),200
        except Exception as e:
            logging.exception("Hit testing failed.",e)
            raise InternalServerError(str(e))

api.add_resource(RAGHitTestingApi, "/rag/datasets/<uuid:dataset_id>/hit-testing")
api.add_resource(RAGBatchHitTestingParamApi, "/rag/datasets/<uuid:dataset_id>/batch-hit-testing")
api.add_resource(RAGBatchHitTestingResultApi, "/rag/datasets/<uuid:dataset_id>/batch-hit-testing")
api.add_resource(RAGBatchHitTestingResultCommentApi, "/rag/datasets/<uuid:dataset_id>/batch-hit-testing/<uuid:query_id>/<uuid:seg_id>/<string:like>")
api.add_resource(RAGBatchHitTestingBusyApi, "/rag/datasets/<uuid:dataset_id>/batch-hit-testing/busy")
api.add_resource(RAGBatchHitTestingSegmentResultApi, "/rag/datasets/<uuid:dataset_id>/batch-hit-testing/result/<string:query_id>")