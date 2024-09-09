from datetime import datetime, timezone
from extensions.ext_redis import redis_client
from flask import request
from werkzeug.exceptions import NotFound
from controllers.console.datasets.error import InvalidMetadataError
from extensions.ext_database import db
from controllers.service_api.dataset.error import (
    InvalidActionError,
)
from fields.document_fields import (
    document_status_fields,
    document_fields,
)
from core.errors.error import (
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from controllers.service_api.app.error import (
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from flask_restful import Resource, fields, marshal, marshal_with, reqparse
from controllers.console.setup import setup_required
from werkzeug.exceptions import Forbidden, NotFound
from sqlalchemy import desc
from fields import document_fields
from controllers.kaas_api import api
from libs.login import current_user, kaas_login_required
from models.dataset import Dataset, DatasetProcessRule, Document, DocumentSegment
from services.dataset_service import DatasetService, DocumentService
from fields.document_fields import (
    document_status_fields,
    document_fields,
)
import services.errors
import services.errors.account
from services.errors.document import DocumentIndexingError
import services.errors.document
from tasks.add_document_to_index_task import add_document_to_index_task
from tasks.remove_document_from_index_task import remove_document_from_index_task


class DocumentListApi(Resource):
    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        tenant_id = str(current_user.current_tenant_id)
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        search = request.args.get('keyword', default=None, type=str)
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()
        if not dataset:
            raise NotFound('Dataset not found.')

        query = Document.query.filter_by(
            dataset_id=str(dataset_id), tenant_id=tenant_id)

        if search:
            search = f'%{search}%'
            query = query.filter(Document.name.like(search))

        query = query.order_by(desc(Document.created_at))

        paginated_documents = query.paginate(
            page=page, per_page=limit, max_per_page=100, error_out=False)
        documents = paginated_documents.items

        response = {
            'data': marshal(documents, document_fields),
            'has_more': len(documents) == limit,
            'limit': limit,
            'total': paginated_documents.total,
            'page': page
        }

        return response


    

class GetProcessRuleApi(Resource):
    @setup_required
    @kaas_login_required
    def get(self):
        req_data = request.args

        document_id = req_data.get('document_id')

        # get default rules
        mode = DocumentService.DEFAULT_RULES['mode']
        rules = DocumentService.DEFAULT_RULES['rules']
        if document_id:
            # get the latest process rule
            document = Document.query.get_or_404(document_id)

            dataset = DatasetService.get_dataset(document.dataset_id)

            if not dataset:
                raise NotFound('Dataset not found.')

            # try:
            #     DatasetService.check_dataset_permission(dataset, current_user)
            # except services.errors.account.NoPermissionError as e:
            #     raise Forbidden(str(e))

            # get the latest process rule
            dataset_process_rule = db.session.query(DatasetProcessRule). \
                filter(DatasetProcessRule.dataset_id == document.dataset_id). \
                order_by(DatasetProcessRule.created_at.desc()). \
                limit(1). \
                one_or_none()
            if dataset_process_rule:
                mode = dataset_process_rule.mode
                rules = dataset_process_rule.rules_dict

        return {
            'mode': mode,
            'rules': rules
        }
def get_document(dataset_id: str, document_id: str) -> Document:
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

class RAGDocumentIndexingStatusApi(Resource):
    @setup_required
    @kaas_login_required
    def get(self, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = get_document(dataset_id, document_id)

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
    

class RAGDocumentDetailApi(Resource):
    METADATA_CHOICES = {"all", "only", "without"}

    def get(self, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = get_document(dataset_id, document_id)

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

    @setup_required
    @kaas_login_required
    def delete(self, dataset_id, document_id):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        # check user's model setting
        DatasetService.check_dataset_model_setting(dataset)

        document = get_document(dataset_id, document_id)

        try:
            DocumentService.delete_document(document)
        except services.errors.document.DocumentIndexingError:
            raise DocumentIndexingError('Cannot delete document during indexing.')

        return {'result': 'success'}, 204    

class AddDocumentToDatasetApi(Resource):
    documents_and_batch_fields = {
        "documents": fields.List(fields.Nested(document_fields)),
        "batch": fields.String,
    }
    @setup_required
    @kaas_login_required
    @marshal_with(documents_and_batch_fields)
    def post(self,  dataset_id):
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


class RAGDocumentRenameApi(Resource):

    @marshal_with(document_fields)
    @setup_required
    @kaas_login_required
    def post(self, dataset_id, document_id):
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

class RAGDocumentStatusApi(Resource):
    @setup_required
    @kaas_login_required
    def patch(self, dataset_id, document_id, action):
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        # check user's model setting
        DatasetService.check_dataset_model_setting(dataset)

        document = get_document(dataset_id, document_id)

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
        
# 获取知识库文档列表    
api.add_resource(DocumentListApi, '/datasets/<uuid:dataset_id>/documents')
# 获取知识库文档处理配置规则
api.add_resource(GetProcessRuleApi, '/datasets/process-rule')
# 获取文档索引状态（之前未使用）
api.add_resource(
    RAGDocumentIndexingStatusApi,
    "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/indexing-status",
)
# 新建文档
api.add_resource(AddDocumentToDatasetApi, "/datasets/<uuid:dataset_id>/documents")
# 获取知识库文档详情，删除知识库文档
api.add_resource(
    RAGDocumentDetailApi, "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>"
)
# 重命名文档
api.add_resource(
    RAGDocumentRenameApi,
    "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/rename",
)
# 操作文档状态接口
api.add_resource(
    RAGDocumentStatusApi,
    "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/status/<string:action>",
)
