import logging

from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal, reqparse,fields
from werkzeug.exceptions import InternalServerError, NotFound
from controllers.console.setup import setup_required
from libs.helper import TimestampField
from libs.login import kaas_login_required
import services
from controllers.kaas_api import api
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
from services.hit_testing_service import HitTestingService




class DatasetQueryApi(Resource):
    dataset_query_detail_fields_with_comment = {
        "id": fields.String,
        "content": fields.String,
        "source": fields.String,
        "source_app_id": fields.String,
        "created_by_role": fields.String,
        "created_by": fields.String,
        "created_at": TimestampField,
        "like": fields.Integer,
        "dislike": fields.Integer,
    }

    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")

        # try:
        #     DatasetService.check_dataset_permission(dataset, current_user)
        # except services.errors.account.NoPermissionError as e:
        #     raise Forbidden(str(e))

        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=20, type=int)

        dataset_queries, total = DatasetService.get_dataset_queries(
            dataset_id=dataset.id, page=page, per_page=limit
        )

        response = {
            "data": marshal(
                dataset_queries,
                DatasetQueryApi.dataset_query_detail_fields_with_comment,
            ),
            "has_more": len(dataset_queries) == limit,
            "limit": limit,
            "total": total,
            "page": page,
        }
        return response, 200
    

    @setup_required
    @kaas_login_required
    def post(self, dataset_id):
        # tenant_id = str(current_user.current_tenant_id)
        dataset_id_str = str(dataset_id)
        # user_id = request.headers.get("User_id", default="123")
        # user = request.headers.get("User", default="123")
        # end_user = (
        #     db.session.query(EndUser)
        #     .filter(
        #         EndUser.tenant_id == tenant_id,
        #         EndUser.external_user_id == user_id,
        #         EndUser.session_id == user,
        #         EndUser.type == "service_api",
        #     )
        #     .first()
        # )

        # if end_user is None:
        #     end_user = EndUser(
        #         tenant_id=tenant_id,
        #         type="service_api",
        #         is_anonymous=False,
        #         name=user,
        #         external_user_id=user_id,
        #         session_id=user,
        #     )
        #     db.session.add(end_user)
        #     db.session.commit()
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
            response = HitTestingService.retrieve(#.retrieve_by_endUser(
                dataset=dataset,
                query=args["query"],
                account=current_user,
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
# 获取查询列表，单条测试    
api.add_resource(DatasetQueryApi, "/hit-testing/datasets/<uuid:dataset_id>")