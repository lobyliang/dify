from flask import request
from datetime import datetime, timezone
from flask_restful import Resource, fields, marshal, marshal_with, reqparse
from controllers.service_api.app.error import (
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from core.errors.error import (
    LLMBadRequestError,
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.indexing_runner import IndexingRunner
from core.rag.extractor.entity.extract_setting import ExtractSetting
from extensions.ext_redis import redis_client
import services
import services.dataset_service
from extensions.ext_database import db
from services.dataset_service import DatasetService, DocumentService
from models.model import UploadFile
from controllers.service_api import api
from controllers.service_api.dataset.error import (
    DocumentAlreadyFinishedError,
    InvalidActionError,
)
from controllers.service_api.wraps import DatasetApiResource
from libs.login import current_user
from models.dataset import Dataset, DatasetProcessRule, Document, DocumentSegment
from services.dataset_service import DatasetService
from werkzeug.exceptions import Forbidden, NotFound
from fields.document_fields import (
    document_status_fields,
    document_fields,
)
import services.errors
import services.errors.account
from tasks.add_document_to_index_task import add_document_to_index_task
from tasks.remove_document_from_index_task import remove_document_from_index_task

# class RAGDatasetQueryApi(DatasetApiResource):

#     def get(self,tenant_id, dataset_id):
#         dataset_id_str = str(dataset_id)
#         dataset = DatasetService.get_dataset(dataset_id_str)
#         if dataset is None:
#             raise NotFound("Dataset not found.")

#         try:
#             DatasetService.check_dataset_permission(dataset, current_user)
#         except services.errors.account.NoPermissionError as e:
#             raise Forbidden(str(e))

#         page = request.args.get('page', default=1, type=int)
#         limit = request.args.get('limit', default=20, type=int)

#         dataset_queries, total = DatasetService.get_dataset_queries(
#             dataset_id=dataset.id,
#             page=page,
#             per_page=limit
#         )

#         response = {
#             'data': marshal(dataset_queries, dataset_query_detail_fields),
#             'has_more': len(dataset_queries) == limit,
#             'limit': limit,
#             'total': total,
#             'page': page
#         }
#         return response, 200


class DatasetIndexingEstimateApi(DatasetApiResource):

    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "info_list", type=dict, required=True, nullable=True, location="json"
        )
        parser.add_argument(
            "process_rule", type=dict, required=True, nullable=True, location="json"
        )
        parser.add_argument(
            "indexing_technique",
            type=str,
            required=True,
            choices=Dataset.INDEXING_TECHNIQUE_LIST,
            nullable=True,
            location="json",
        )
        parser.add_argument(
            "doc_form",
            type=str,
            default="text_model",
            required=False,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "dataset_id", type=str, required=False, nullable=False, location="json"
        )
        parser.add_argument(
            "doc_language",
            type=str,
            default="English",
            required=False,
            nullable=False,
            location="json",
        )
        args = parser.parse_args()
        # validate args
        DocumentService.estimate_args_validate(args)
        extract_settings = []
        if args["info_list"]["data_source_type"] == "upload_file":
            file_ids = args["info_list"]["file_info_list"]["file_ids"]
            file_details = (
                db.session.query(UploadFile)
                .filter(
                    UploadFile.tenant_id == current_user.current_tenant_id,
                    UploadFile.id.in_(file_ids),
                )
                .all()
            )

            if file_details is None:
                raise NotFound("File not found.")

            if file_details:
                for file_detail in file_details:
                    extract_setting = ExtractSetting(
                        datasource_type="upload_file",
                        upload_file=file_detail,
                        document_model=args["doc_form"],
                    )
                    extract_settings.append(extract_setting)
        elif args["info_list"]["data_source_type"] == "notion_import":
            notion_info_list = args["info_list"]["notion_info_list"]
            for notion_info in notion_info_list:
                workspace_id = notion_info["workspace_id"]
                for page in notion_info["pages"]:
                    extract_setting = ExtractSetting(
                        datasource_type="notion_import",
                        notion_info={
                            "notion_workspace_id": workspace_id,
                            "notion_obj_id": page["page_id"],
                            "notion_page_type": page["type"],
                            "tenant_id": current_user.current_tenant_id,
                        },
                        document_model=args["doc_form"],
                    )
                    extract_settings.append(extract_setting)
        else:
            raise ValueError("Data source type not support")
        indexing_runner = IndexingRunner()
        try:
            response = indexing_runner.indexing_estimate(
                current_user.current_tenant_id,
                extract_settings,
                args["process_rule"],
                args["doc_form"],
                args["doc_language"],
                args["dataset_id"],
                args["indexing_technique"],
            )
        except LLMBadRequestError:
            raise ProviderNotInitializeError(
                "No Embedding Model available. Please configure a valid provider "
                "in the Settings -> Model Provider."
            )
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)

        return response, 200


class DocumentResource(DatasetApiResource):
    def get_document(self, dataset_id: str, document_id: str) -> Document:
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound("Dataset not found.")

        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        document = DocumentService.get_document(dataset_id, document_id)

        if not document:
            raise NotFound("Document not found.")

        if document.tenant_id != current_user.current_tenant_id:
            raise Forbidden("No permission.")

        return document

    def get_batch_documents(self, dataset_id: str, batch: str) -> list[Document]:
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound("Dataset not found.")

        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        documents = DocumentService.get_batch_documents(dataset_id, batch)

        if not documents:
            raise NotFound("Documents not found.")

        return documents


class RAGDocumentBatchIndexingEstimateApi(DocumentResource):

    def get(self, tenant_id, dataset_id, batch):
        dataset_id = str(dataset_id)
        batch = str(batch)
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        documents = self.get_batch_documents(dataset_id, batch)
        response = {
            "tokens": 0,
            "total_price": 0,
            "currency": "USD",
            "total_segments": 0,
            "preview": [],
        }
        if not documents:
            return response
        data_process_rule = documents[0].dataset_process_rule
        data_process_rule_dict = data_process_rule.to_dict()
        info_list = []
        extract_settings = []
        # account = Account.get_by_openid('loby','123')
        # taj = db.session.query(TenantAccountJoin).filter(TenantAccountJoin.account_id==account.id).first()

        for document in documents:
            if document.indexing_status in ["completed", "error"]:
                raise DocumentAlreadyFinishedError()
            data_source_info = document.data_source_info_dict
            # format document files info
            if data_source_info and "upload_file_id" in data_source_info:
                file_id = data_source_info["upload_file_id"]
                info_list.append(file_id)
            # format document notion info
            elif (
                data_source_info
                and "notion_workspace_id" in data_source_info
                and "notion_page_id" in data_source_info
            ):
                pages = []
                page = {
                    "page_id": data_source_info["notion_page_id"],
                    "type": data_source_info["type"],
                }
                pages.append(page)
                notion_info = {
                    "workspace_id": data_source_info["notion_workspace_id"],
                    "pages": pages,
                }
                info_list.append(notion_info)

            if document.data_source_type == "upload_file":
                file_id = data_source_info["upload_file_id"]
                file_detail = (
                    db.session.query(UploadFile)
                    .filter(UploadFile.tenant_id == tenant_id, UploadFile.id == file_id)
                    .first()
                )

                if file_detail is None:
                    raise NotFound("File not found.")

                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file_detail,
                    document_model=document.doc_form,
                )
                extract_settings.append(extract_setting)

            elif document.data_source_type == "notion_import":
                extract_setting = ExtractSetting(
                    datasource_type="notion_import",
                    notion_info={
                        "notion_workspace_id": data_source_info["notion_workspace_id"],
                        "notion_obj_id": data_source_info["notion_page_id"],
                        "notion_page_type": data_source_info["type"],
                        "tenant_id": tenant_id,  # current_user.current_tenant_id
                    },
                    document_model=document.doc_form,
                )
                extract_settings.append(extract_setting)

            else:
                raise ValueError("Data source type not support")
            indexing_runner = IndexingRunner()
            try:
                response = indexing_runner.indexing_estimate(
                    tenant_id,
                    extract_settings,  # current_user.current_tenant_id
                    data_process_rule_dict,
                    document.doc_form,
                    "English",
                    dataset_id,
                )
            except LLMBadRequestError:
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider."
                )
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)
        return response


class RAGDocumentBatchIndexingStatusApi(DocumentResource):

    def get(self, tenant_id, dataset_id, batch):
        dataset_id = str(dataset_id)
        batch = str(batch)
        documents = self.get_batch_documents(dataset_id, batch)
        documents_status = []
        for document in documents:
            completed_segments = DocumentSegment.query.filter(
                DocumentSegment.completed_at.isnot(None),
                DocumentSegment.document_id == str(document.id),
                DocumentSegment.status != "re_segment",
            ).count()
            total_segments = DocumentSegment.query.filter(
                DocumentSegment.document_id == str(document.id),
                DocumentSegment.status != "re_segment",
            ).count()
            document.completed_segments = completed_segments
            document.total_segments = total_segments
            if document.is_paused:
                document.indexing_status = "paused"
            documents_status.append(marshal(document, document_status_fields))
        data = {"data": documents_status}
        return data


# -----------------------------


class GetProcessRuleApi(Resource):

    def get(self):
        req_data = request.args

        document_id = req_data.get("document_id")

        # get default rules
        mode = DocumentService.DEFAULT_RULES["mode"]
        rules = DocumentService.DEFAULT_RULES["rules"]
        if document_id:
            # get the latest process rule
            document = Document.query.get_or_404(document_id)

            dataset = DatasetService.get_dataset(document.dataset_id)

            if not dataset:
                raise NotFound("Dataset not found.")

            # try:
            #     DatasetService.check_dataset_permission(dataset, current_user)
            # except services.errors.account.NoPermissionError as e:
            #     raise Forbidden(str(e))

            # get the latest process rule
            dataset_process_rule = (
                db.session.query(DatasetProcessRule)
                .filter(DatasetProcessRule.dataset_id == document.dataset_id)
                .order_by(DatasetProcessRule.created_at.desc())
                .limit(1)
                .one_or_none()
            )
            if dataset_process_rule:
                mode = dataset_process_rule.mode
                rules = dataset_process_rule.rules_dict

        return {"mode": mode, "rules": rules}


class RAGDocumentIndexingStatusApi(DocumentResource):

    def get(self, tenant_id, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = self.get_document(dataset_id, document_id)

        completed_segments = DocumentSegment.query.filter(
            DocumentSegment.completed_at.isnot(None),
            DocumentSegment.document_id == str(document_id),
            DocumentSegment.status != "re_segment",
        ).count()
        total_segments = DocumentSegment.query.filter(
            DocumentSegment.document_id == str(document_id),
            DocumentSegment.status != "re_segment",
        ).count()

        document.completed_segments = completed_segments
        document.total_segments = total_segments
        if document.is_paused:
            document.indexing_status = "paused"
        return marshal(document, document_status_fields)


class RAGDocumentIndexingEstimateApi(DocumentResource):

    def get(self, tenant_id, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = self.get_document(dataset_id, document_id)

        if document.indexing_status in ["completed", "error"]:
            raise DocumentAlreadyFinishedError()

        data_process_rule = document.dataset_process_rule
        data_process_rule_dict = data_process_rule.to_dict()

        response = {
            "tokens": 0,
            "total_price": 0,
            "currency": "USD",
            "total_segments": 0,
            "preview": [],
        }

        if document.data_source_type == "upload_file":
            data_source_info = document.data_source_info_dict
            if data_source_info and "upload_file_id" in data_source_info:
                file_id = data_source_info["upload_file_id"]

                file = (
                    db.session.query(UploadFile)
                    .filter(
                        UploadFile.tenant_id == document.tenant_id,
                        UploadFile.id == file_id,
                    )
                    .first()
                )

                # raise error if file not found
                if not file:
                    raise NotFound("File not found.")

                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file,
                    document_model=document.doc_form,
                )

                indexing_runner = IndexingRunner()

                try:
                    # account = Account.get_by_openid('loby','123')
                    # taj = db.session.query(TenantAccountJoin).filter(TenantAccountJoin.account_id==account.id).first()

                    response = indexing_runner.indexing_estimate(
                        tenant_id,
                        [extract_setting],
                        data_process_rule_dict,
                        document.doc_form,
                        "Chinese",
                        dataset_id,
                    )
                except LLMBadRequestError:
                    raise ProviderNotInitializeError(
                        "No Embedding Model available. Please configure a valid provider "
                        "in the Settings -> Model Provider."
                    )
                except ProviderTokenNotInitError as ex:
                    raise ProviderNotInitializeError(ex.description)

        return response


class AddDocumentToDatasetApi(DatasetApiResource):
    documents_and_batch_fields = {
        "documents": fields.List(fields.Nested(document_fields)),
        "batch": fields.String,
    }

    @marshal_with(documents_and_batch_fields)
    def post(self, tenant_id, dataset_id):
        dataset_id = str(dataset_id)
        # user = request.headers.get('user')
        # user_id = request.headers.get('user_id')
        dataset = DatasetService.get_dataset(dataset_id)
        # account = TenantService.get_tenant_creater(tenant_id)
        if not dataset:
            raise NotFound("Dataset not found.")

        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        parser = reqparse.RequestParser()
        parser.add_argument(
            "indexing_technique",
            type=str,
            choices=Dataset.INDEXING_TECHNIQUE_LIST,
            nullable=False,
            location="json",
        )
        parser.add_argument("data_source", type=dict, required=False, location="json")
        parser.add_argument("process_rule", type=dict, required=False, location="json")
        parser.add_argument(
            "duplicate", type=bool, default=True, nullable=False, location="json"
        )
        parser.add_argument(
            "original_document_id", type=str, required=False, location="json"
        )
        parser.add_argument(
            "doc_form",
            type=str,
            default="text_model",
            required=False,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "doc_language",
            type=str,
            default="English",
            required=False,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "retrieval_model",
            type=dict,
            required=False,
            nullable=False,
            location="json",
        )
        args = parser.parse_args()

        if not dataset.indexing_technique and not args["indexing_technique"]:
            raise ValueError("indexing_technique is required.")

        # validate args
        DocumentService.document_create_args_validate(args)

        try:
            documents, batch = DocumentService.save_document_with_dataset_id(
                dataset, args, current_user
            )

        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()

        return {"documents": documents, "batch": batch}


class RAGDocumentStatusApi(DocumentResource):

    def patch(self, tenant_id, dataset_id, document_id, action):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        # check user's model setting
        DatasetService.check_dataset_model_setting(dataset)

        document = self.get_document(dataset_id, document_id)

        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        indexing_cache_key = "document_{}_indexing".format(document.id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is not None:
            raise InvalidActionError(
                "Document is being indexed, please try again later"
            )

        if action == "enable":
            if document.enabled:
                raise InvalidActionError("Document already enabled.")

            document.enabled = True
            document.disabled_at = None
            document.disabled_by = None
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # Set cache to prevent indexing the same document multiple times
            redis_client.setex(indexing_cache_key, 600, 1)

            add_document_to_index_task.delay(document_id)

            return {"result": "success"}, 200

        elif action == "disable":
            if not document.completed_at or document.indexing_status != "completed":
                raise InvalidActionError("Document is not completed.")
            if not document.enabled:
                raise InvalidActionError("Document already disabled.")

            document.enabled = False
            document.disabled_at = datetime.now(timezone.utc).replace(tzinfo=None)
            document.disabled_by = current_user.id
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # Set cache to prevent indexing the same document multiple times
            redis_client.setex(indexing_cache_key, 600, 1)

            remove_document_from_index_task.delay(document_id)

            return {"result": "success"}, 200

        elif action == "archive":
            if document.archived:
                raise InvalidActionError("Document already archived.")

            document.archived = True
            document.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
            document.archived_by = current_user.id
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            if document.enabled:
                # Set cache to prevent indexing the same document multiple times
                redis_client.setex(indexing_cache_key, 600, 1)

                remove_document_from_index_task.delay(document_id)

            return {"result": "success"}, 200
        elif action == "un_archive":
            if not document.archived:
                raise InvalidActionError("Document is not archived.")

            document.archived = False
            document.archived_at = None
            document.archived_by = None
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # Set cache to prevent indexing the same document multiple times
            redis_client.setex(indexing_cache_key, 600, 1)

            add_document_to_index_task.delay(document_id)

            return {"result": "success"}, 200
        else:
            raise InvalidActionError()


# #-----------已使用--------------
# api.add_resource(RAGDatasetQueryApi, '/datasets/<uuid:dataset_id>/queries')
# -----------已使用--------------
api.add_resource(DatasetIndexingEstimateApi, "/datasets/indexing-estimate")
# -----------已使用--------------
api.add_resource(
    RAGDocumentBatchIndexingEstimateApi,
    "/rag/datasets/<uuid:dataset_id>/batch/<string:batch>/indexing-estimate",
)
# -----------已使用--------------
api.add_resource(
    RAGDocumentBatchIndexingStatusApi,
    "/rag/datasets/<uuid:dataset_id>/batch/<string:batch>/indexing-status",
)

# -----------已使用--------------
api.add_resource(GetProcessRuleApi, "/datasets/process-rule")

# -----------已使用--------------
api.add_resource(
    RAGDocumentIndexingStatusApi,
    "/rag/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/indexing-status",
)
# -----------已使用--------------
api.add_resource(
    RAGDocumentIndexingEstimateApi,
    "/rag/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/indexing-estimate",
)
#############################################
# -----------已使用--------------
api.add_resource(AddDocumentToDatasetApi, "/rag/datasets/<uuid:dataset_id>/documents")

# -----------已使用--------------
api.add_resource(
    RAGDocumentStatusApi,
    "/rag/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/status/<string:action>",
)
