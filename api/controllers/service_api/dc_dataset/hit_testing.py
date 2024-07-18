import logging

from flask import request
from flask_restful import marshal, reqparse
from werkzeug.exceptions import InternalServerError, NotFound
from extensions.ext_database import db
from controllers.service_api.wraps import DatasetApiResource
from models.model import EndUser
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


api.add_resource(RAGHitTestingApi, "/rag/datasets/<uuid:dataset_id>/hit-testing")
