import logging
from flask_restful import fields

# from requests import request
from flask import request
from controllers.service_api.dataset.dataset import _validate_name
from controllers.service_api.dataset.error import (
    DocumentIndexingError,
    InvalidMetadataError,
)
from controllers.service_api.dc_dataset.ds_create import DocumentResource
from core.model_runtime.entities.model_entities import ModelType
from fields.document_fields import document_fields
from fields.app_fields import related_app_list
from core.provider_manager import ProviderManager
from libs.helper import TimestampField
from werkzeug.exceptions import NotFound
from controllers.service_api.wraps import DatasetApiResource
from core.rag.retrieval.dc_retrieval.custom_dataset_retrieval import (
    CustomDataSetRetrieval,
)
from controllers.service_api import api
from flask_restful import marshal, marshal_with, reqparse
from fields.dataset_fields import dataset_detail_fields
from models.dataset import Dataset
import services
from services.account_service import TenantService
from services.dataset_service import DatasetService, DocumentService
import services.errors
import services.errors.document


class RAGQueryApi(DatasetApiResource):
    def post(
        self,
        tenant_id,
    ):

        parser = reqparse.RequestParser()
        parser.add_argument(
            "user_id", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "app_id", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "retrieve_strategy",
            type=str,
            choices=["single", "multiple"],
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "search_method",
            type=str,
            choices=[
                "keyword_search",
                "semantic_search",
                "full_text_search",
                "hybrid_search",
            ],
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "dataset_ids", type=list, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "reorgenaize",
            type=bool,
            default=True,
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "is_agent",
            type=bool,
            default=True,
            required=True,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "top_k", type=int, default=1, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "score_threshold",
            type=float,
            default=0.7,
            required=False,
            nullable=True,
            location="json",
        )
        parser.add_argument(
            "query", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "show_source", type=bool, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "attach_detail",
            type=bool,
            required=False,
            nullable=True,
            default=False,
            location="json",
        )
        args = parser.parse_args()
        user_id = args["user_id"]
        app_id = args["app_id"]
        retrieve_strategy = args["retrieve_strategy"]
        search_method = args["search_method"]
        dataset_ids = args["dataset_ids"]
        reorgenaize = args["reorgenaize"]
        is_agent = args["is_agent"]
        query = args["query"]
        show_source = args["show_source"]
        tok_k = args["top_k"]
        score_threshold = args["score_threshold"]
        attach_detail = args["attach_detail"]
        # get dataset
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return (
            custom_dataset_retrieval.retrieval(
                user_id=user_id,
                app_id=app_id,
                retrieve_strategy=retrieve_strategy,
                search_method=search_method,
                dataset_ids=dataset_ids,
                reorgenazie_output=reorgenaize,
                query=query,
                invoke_from="service-api",
                show_retrieve_source=show_source,
                tenant_id=tenant_id,
                top_k=tok_k,
                score_threshold=score_threshold,
                hit_callback=None,
                is_agent = is_agent,
                # attach_detail=attach_detail,
            ),
            200,
        )


class DatasetQueryApi(DatasetApiResource):
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

    def get(self, tenant_id, dataset_id):
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


class RAGDataSetListApi(DatasetApiResource):
    def get(
        self,
        tenant_id,
    ):
        # aut = currentRequest.headers.get('Authorization')
        # if not current_user.is_admin_or_owner:
        #     raise aut
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return custom_dataset_retrieval.get_datasets(tenant_id), 200


chunck_fields = {
    "id": fields.String,
    "index_node_id": fields.String,
    "doc_id": fields.String,
    "status": fields.String,
    "keywords": fields.List(fields.String),
    "hit_count": fields.Integer,
    "enabled": fields.Boolean,
    "created_by": fields.String,
    "created_at": TimestampField,
    "updated_by": fields.String,
    "content": fields.String,
    "answer": fields.String,
    "position": fields.Integer,
    "tokens": fields.Integer,
    "word_count": fields.Integer,
}


class RAGChunckListApi(DatasetApiResource):

    @marshal_with(chunck_fields)
    def get(self, tenant_id, doc_id, page_no, page_size):
        doc_id = str(doc_id)
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return (
            custom_dataset_retrieval.get_chuncks_by_order(
                doc_id=doc_id, page_number=page_no, page_size=page_size
            ),
            200,
        )


class RAGCommnetApi(DatasetApiResource):

    def post(self, tenant_id, query_id: str, seg_id: str, like: str):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "rate", type=float, required=True, nullable=False, location="args"
        )
        args = parser.parse_args()
        rate = args["rate"]
        CustomDataSetRetrieval.comment_rag_query(
            query_id=query_id, like=like, seg_id=seg_id, rate=rate
        )
        return {"msg": "success"}, 200


def _validate_description_length(description):
    if len(description) > 400:
        raise ValueError("Description cannot exceed 400 characters.")
    return description


# Loby
class RAGDatasetApi(DatasetApiResource):

    def get(self, tenant_id, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")
        # try:
        #     DatasetService.check_dataset_permission(
        #         dataset, current_user)
        # except services.errors.account.NoPermissionError as e:
        #     raise Forbidden(str(e))
        data = marshal(dataset, dataset_detail_fields)
        # check embedding setting
        provider_manager = ProviderManager()
        configurations = provider_manager.get_configurations(tenant_id=tenant_id)

        embedding_models = configurations.get_models(
            model_type=ModelType.TEXT_EMBEDDING, only_active=True
        )

        model_names = []
        for embedding_model in embedding_models:
            model_names.append(
                f"{embedding_model.model}:{embedding_model.provider.provider}"
            )

        if data["indexing_technique"] == "high_quality":
            item_model = f"{data['embedding_model']}:{data['embedding_model_provider']}"
            if item_model in model_names:
                data["embedding_available"] = True
            else:
                data["embedding_available"] = False
        else:
            data["embedding_available"] = True
        return data, 200

    def patch(self, tenant_id, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")
        # check user's model setting
        DatasetService.check_dataset_model_setting(dataset)

        parser = reqparse.RequestParser()
        parser.add_argument(
            "name",
            nullable=False,
            help="type is required. Name must be between 1 to 40 characters.",
            type=_validate_name,
        )
        parser.add_argument(
            "description",
            location="json",
            store_missing=False,
            type=_validate_description_length,
        )
        parser.add_argument(
            "indexing_technique",
            type=str,
            location="json",
            choices=Dataset.INDEXING_TECHNIQUE_LIST,
            nullable=True,
            help="Invalid indexing technique.",
        )
        parser.add_argument(
            "permission",
            type=str,
            location="json",
            choices=("only_me", "all_team_members"),
            help="Invalid permission.",
        )
        parser.add_argument(
            "embedding_model",
            type=str,
            location="json",
            help="Invalid embedding model.",
        )
        parser.add_argument(
            "embedding_model_provider",
            type=str,
            location="json",
            help="Invalid embedding model provider.",
        )
        parser.add_argument(
            "retrieval_model",
            type=dict,
            location="json",
            help="Invalid retrieval model.",
        )
        args = parser.parse_args()

        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()
        account = TenantService.get_tenant_creater(tenant_id=tenant_id)

        dataset = DatasetService.update_dataset(dataset_id_str, args, account)

        if dataset is None:
            raise NotFound("Dataset not found.")

        return marshal(dataset, dataset_detail_fields), 200

    def delete(self, tenant_id, dataset_id):
        dataset_id_str = str(dataset_id)

        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()
        account = TenantService.get_tenant_creater(tenant_id=tenant_id)
        if DatasetService.delete_dataset(dataset_id_str, account):
            return {"result": "success"}, 204
        else:
            raise NotFound("Dataset not found.")


class RAGDocumentDetailApi(DocumentResource):
    METADATA_CHOICES = {"all", "only", "without"}

    def get(self, tenant_id, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = self.get_document(dataset_id, document_id)

        metadata = request.args.get("metadata", "all")
        if metadata not in self.METADATA_CHOICES:
            raise InvalidMetadataError(f"Invalid metadata value: {metadata}")

        if metadata == "only":
            response = {
                "id": document.id,
                "doc_type": document.doc_type,
                "doc_metadata": document.doc_metadata,
            }
        elif metadata == "without":
            process_rules = DatasetService.get_process_rules(dataset_id)
            data_source_info = document.data_source_detail_dict
            response = {
                "id": document.id,
                "position": document.position,
                "data_source_type": document.data_source_type,
                "data_source_info": data_source_info,
                "dataset_process_rule_id": document.dataset_process_rule_id,
                "dataset_process_rule": process_rules,
                "name": document.name,
                "created_from": document.created_from,
                "created_by": document.created_by,
                "created_at": document.created_at.timestamp(),
                "tokens": document.tokens,
                "indexing_status": document.indexing_status,
                "completed_at": (
                    int(document.completed_at.timestamp())
                    if document.completed_at
                    else None
                ),
                "updated_at": (
                    int(document.updated_at.timestamp())
                    if document.updated_at
                    else None
                ),
                "indexing_latency": document.indexing_latency,
                "error": document.error,
                "enabled": document.enabled,
                "disabled_at": (
                    int(document.disabled_at.timestamp())
                    if document.disabled_at
                    else None
                ),
                "disabled_by": document.disabled_by,
                "archived": document.archived,
                "segment_count": document.segment_count,
                "average_segment_length": document.average_segment_length,
                "hit_count": document.hit_count,
                "display_status": document.display_status,
                "doc_form": document.doc_form,
            }
        else:
            process_rules = DatasetService.get_process_rules(dataset_id)
            data_source_info = document.data_source_detail_dict
            response = {
                "id": document.id,
                "position": document.position,
                "data_source_type": document.data_source_type,
                "data_source_info": data_source_info,
                "dataset_process_rule_id": document.dataset_process_rule_id,
                "dataset_process_rule": process_rules,
                "name": document.name,
                "created_from": document.created_from,
                "created_by": document.created_by,
                "created_at": document.created_at.timestamp(),
                "tokens": document.tokens,
                "indexing_status": document.indexing_status,
                "completed_at": (
                    int(document.completed_at.timestamp())
                    if document.completed_at
                    else None
                ),
                "updated_at": (
                    int(document.updated_at.timestamp())
                    if document.updated_at
                    else None
                ),
                "indexing_latency": document.indexing_latency,
                "error": document.error,
                "enabled": document.enabled,
                "disabled_at": (
                    int(document.disabled_at.timestamp())
                    if document.disabled_at
                    else None
                ),
                "disabled_by": document.disabled_by,
                "archived": document.archived,
                "doc_type": document.doc_type,
                "doc_metadata": document.doc_metadata,
                "segment_count": document.segment_count,
                "average_segment_length": document.average_segment_length,
                "hit_count": document.hit_count,
                "display_status": document.display_status,
                "doc_form": document.doc_form,
            }

        return response, 200


class RAGDatasetRelatedAppListApi(DocumentResource):

    @marshal_with(related_app_list)
    def get(self, tenant_id, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")

        # try:
        #     DatasetService.check_dataset_permission(dataset, current_user)
        # except services.errors.account.NoPermissionError as e:
        #     raise Forbidden(str(e))

        app_dataset_joins = DatasetService.get_related_apps(dataset.id)

        related_apps = []
        for app_dataset_join in app_dataset_joins:
            app_model = app_dataset_join.app
            if app_model:
                related_apps.append(app_model)

        return {"data": related_apps, "total": len(related_apps)}, 200


class RAGDocumentRenameApi(DocumentResource):

    @marshal_with(document_fields)
    def post(self, tenant_id, dataset_id, document_id):
        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument(
            "name", type=str, required=True, nullable=False, location="json"
        )
        args = parser.parse_args()

        try:
            document = DocumentService.rename_document(
                dataset_id, document_id, args["name"]
            )
        except services.errors.document.DocumentIndexingError:
            raise DocumentIndexingError("Cannot delete document during indexing.")

        return document


class RAGCommnetListApi(DocumentResource):

    # @marshal_with(document_fields)
    def get(self, tenant_id, dataset_id):
        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument(
            "page_no", type=int, required=True, nullable=False, location="args"
        )
        parser.add_argument(
            "page_size", type=int, required=True, nullable=False, location="args"
        )
        args = parser.parse_args()
        page_no = args["page_no"]
        page_size = args["page_size"]
        try:
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.dataset_comment_list(
                dataset_id, page_no, page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200


class RAGDocumentCommnetListApi(DocumentResource):

    # @marshal_with(document_fields)
    def get(self, tenant_id, dataset_id):
        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()

        # parser = reqparse.RequestParser()
        # parser.add_argument('name', type=str, required=True, nullable=False, location='json')
        # args = parser.parse_args()

        try:
            parser = reqparse.RequestParser()
            parser.add_argument(
                "page_no", type=int, required=True, nullable=False, location="args"
            )
            parser.add_argument(
                "page_size", type=int, required=True, nullable=False, location="args"
            )
            args = parser.parse_args()
            page_no = args["page_no"]
            page_size = args["page_size"]
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.document_comment_list_in_dataset(
                dataset_id, page_no=page_no, page_size=page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200


class RAGChunkCommnetListApi(DocumentResource):

    # @marshal_with(document_fields)
    def get(self, tenant_id, segment_id: str):
        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()

        # parser = reqparse.RequestParser()
        # parser.add_argument('name', type=str, required=True, nullable=False, location='json')
        # args = parser.parse_args()

        try:
            parser = reqparse.RequestParser()
            parser.add_argument(
                "page_no", type=int, required=True, nullable=False, location="args"
            )
            parser.add_argument(
                "page_size", type=int, required=True, nullable=False, location="args"
            )
            args = parser.parse_args()
            page_no = args["page_no"]
            page_size = args["page_size"]
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.chunck_comment_list(
                str(segment_id), page_no=page_no, page_size=page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200


api.add_resource(RAGChunkCommnetListApi, "/rag/datasets/chunck/<uuid:segment_id>")
api.add_resource(RAGDatasetApi, "/rag/datasets/<uuid:dataset_id>")
api.add_resource(
    RAGCommnetApi, "/rag/query/<string:query_id>/<string:seg_id>/comment/<string:like>"
)
api.add_resource(RAGCommnetListApi, "/rag/datasets/<uuid:dataset_id>/comments")
api.add_resource(
    RAGDocumentCommnetListApi, "/rag/datasets/<uuid:dataset_id>/documents/comments"
)
api.add_resource(RAGQueryApi, "/rag/query")
api.add_resource(RAGDataSetListApi, "/rag/list")
api.add_resource(
    RAGChunckListApi, "/rag/<uuid:doc_id>/chuncks/<int:page_no>/<int:page_size>"
)
api.add_resource(DatasetQueryApi, "/rag/datasets/<uuid:dataset_id>/queries")
api.add_resource(
    RAGDocumentDetailApi, "/rag/datasets/<uuid:dataset_id>/documents/<uuid:document_id>"
)
api.add_resource(
    RAGDatasetRelatedAppListApi, "/rag/datasets/<uuid:dataset_id>/related-apps"
)
api.add_resource(
    RAGDocumentRenameApi,
    "/rag/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/rename",
)
