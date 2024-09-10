from flask import request
from flask_restful import Resource, marshal, marshal_with, reqparse
from werkzeug.exceptions import NotFound,Forbidden
from controllers.kaas_api.wraps import validate_dream_ai_token
from extensions.ext_database import db
from controllers.console.app.error import ProviderNotInitializeError
from controllers.console.setup import setup_required
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.indexing_runner import IndexingRunner
from core.rag.extractor.entity.extract_setting import ExtractSetting
from models.model import UploadFile
import services.dataset_service
from controllers.kaas_api import api
from controllers.service_api.dataset.error import DatasetInUseError, DatasetNameDuplicateError
from fields.app_fields import related_app_list
from core.model_runtime.entities.model_entities import ModelType
from core.provider_manager import ProviderManager
from fields.dataset_fields import dataset_detail_fields
from libs.login import current_user, kaas_login_required
from models.dataset import Dataset, DocumentSegment
from services.dataset_service import DatasetService, DocumentService
from fields.document_fields import (
    document_status_fields,
)
from services.dc_dream_ai_service import DreamAIService
def _validate_name(name):
    if not name or len(name) < 1 or len(name) > 40:
        raise ValueError('Name must be between 1 to 40 characters.')
    return name


def _validate_description_length(description):
    if len(description) > 400:
        raise ValueError('Description cannot exceed 400 characters.')
    return description


class DatasetListApi(Resource):
    """Resource for datasets."""

    @setup_required
    @kaas_login_required
    @validate_dream_ai_token(funcs={'and':['kaas:public']})
    def get(self):
        """Resource for getting datasets."""
        if not DreamAIService.check_permission({'and':['kaas:create_public','kaas:private']}):
            raise Forbidden("对不起，您无权创建知识库。")
        tenant_id = str(current_user.current_tenant_id)
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        provider = request.args.get('provider', default="vendor")
        search = request.args.get('keyword', default=None, type=str)
        tag_ids = request.args.getlist('tag_ids')

        datasets, total = DatasetService.get_datasets(page, limit, provider,
                                                      tenant_id, current_user, search, tag_ids)
        # check embedding setting
        provider_manager = ProviderManager()
        configurations = provider_manager.get_configurations(
            tenant_id=str(current_user.current_tenant_id)
        )

        embedding_models = configurations.get_models(
            model_type=ModelType.TEXT_EMBEDDING,
            only_active=True
        )

        model_names = []
        for embedding_model in embedding_models:
            model_names.append(f"{embedding_model.model}:{embedding_model.provider.provider}")

        data = marshal(datasets, dataset_detail_fields)
        for item in data:
            if item['indexing_technique'] == 'high_quality':
                item_model = f"{item['embedding_model']}:{item['embedding_model_provider']}"
                if item_model in model_names:
                    item['embedding_available'] = True
                else:
                    item['embedding_available'] = False
            else:
                item['embedding_available'] = True
        response = {
            'data': data,
            'has_more': len(datasets) == limit,
            'limit': limit,
            'total': total,
            'page': page
        }
        return response, 200

    @setup_required
    @kaas_login_required
    @validate_dream_ai_token(funcs={'and':['kaas:public']})
    def post(self):
        """Resource for creating datasets."""
        tenant_id = str(current_user.current_tenant_id)
        parser = reqparse.RequestParser()
        parser.add_argument('name', nullable=False, required=True,
                            help='type is required. Name must be between 1 to 40 characters.',
                            type=_validate_name)
        parser.add_argument('indexing_technique', type=str, location='json',
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            help='Invalid indexing technique.')
        args = parser.parse_args()

        try:
            dataset = DatasetService.create_empty_dataset(
                tenant_id=tenant_id,
                name=args['name'],
                indexing_technique=args['indexing_technique'],
                account=current_user
            )
        except services.errors.dataset.DatasetNameDuplicateError:
            raise DatasetNameDuplicateError()

        return marshal(dataset, dataset_detail_fields), 200
    
class RAGDatasetApi(Resource):

    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        tenant_id = str(current_user.current_tenant_id)
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")

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

    @setup_required
    @kaas_login_required
    def patch(self, dataset_id):
        # tenant_id = current_user.current_tenant_id
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
        # account = TenantService.get_tenant_creater(tenant_id=tenant_id)

        if args['permission'] == 'all_team_members' and \
            not DreamAIService.check_permission({'and':['kaas:create_public']}): # check dream ai token
            raise Forbidden("对不起，您无权编辑公共知识库。")
        if args['permission'] == 'only_me' and \
            not DreamAIService.check_permission({'and':['kaas:private']}):
                raise Forbidden("对不起，您无权管理知识库。")
        
        dataset = DatasetService.update_dataset(dataset_id_str, args, current_user)

        if dataset is None:
            raise NotFound("Dataset not found.")

        return marshal(dataset, dataset_detail_fields), 200
    
    @setup_required
    @kaas_login_required
    def delete(self, dataset_id):
        """
        Deletes a dataset given its ID.

        Args:
            dataset_id (UUID): The ID of the dataset to be deleted.

        Returns:
            dict: A dictionary with a key 'result' and a value 'success' 
                  if the dataset was successfully deleted. Omitted in HTTP response.
            int: HTTP status code 204 indicating that the operation was successful.

        Raises:
            NotFound: If the dataset with the given ID does not exist.
        """

        dataset_id_str = str(dataset_id)

        try:
            
            dataset = DatasetService.get_dataset(dataset_id_str)
            if dataset:
                if dataset.permission == 'only_me' and (not DreamAIService.check_permission({'and':['kaas:private']}) \
                    or dataset.created_by != current_user.id): # check dream ai token
                    raise Forbidden("对不起，您无权删除知识库。")
                elif dataset.permission == 'all_team_members' and not DreamAIService.check_permission({'and':['kaas:del_public']}): # check dream ai token
                    raise Forbidden("对不起，您无权删除公共知识库。")
                         
                if DatasetService.delete_dataset(dataset_id_str, current_user):
                    return {'result': 'success'}, 204
                else:
                    raise NotFound("Dataset not found.")
        except services.errors.dataset.DatasetInUseError:
            raise DatasetInUseError()    
    

class RAGDatasetRelatedAppListApi(Resource):

    @marshal_with(related_app_list)
    @setup_required
    @kaas_login_required    
    @validate_dream_ai_token(funcs={'and':['kaas:agent']})
    def get(self,  dataset_id):
        # tenant_id = str(current_user.current_tenant_id)
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
        

class DatasetIndexingEstimateApi(Resource):

    @setup_required
    @kaas_login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('info_list', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('process_rule', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('indexing_technique', type=str, required=True,
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            nullable=True, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('dataset_id', type=str, required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        args = parser.parse_args()
        # validate args
        DocumentService.estimate_args_validate(args)
        extract_settings = []
        if args['info_list']['data_source_type'] == 'upload_file':
            file_ids = args['info_list']['file_info_list']['file_ids']
            file_details = db.session.query(UploadFile).filter(
                UploadFile.tenant_id == current_user.current_tenant_id,
                UploadFile.id.in_(file_ids)
            ).all()

            if file_details is None:
                raise NotFound("File not found.")

            if file_details:
                for file_detail in file_details:
                    extract_setting = ExtractSetting(
                        datasource_type="upload_file",
                        upload_file=file_detail,
                        document_model=args['doc_form']
                    )
                    extract_settings.append(extract_setting)
        elif args['info_list']['data_source_type'] == 'notion_import':
            notion_info_list = args['info_list']['notion_info_list']
            for notion_info in notion_info_list:
                workspace_id = notion_info['workspace_id']
                for page in notion_info['pages']:
                    extract_setting = ExtractSetting(
                        datasource_type="notion_import",
                        notion_info={
                            "notion_workspace_id": workspace_id,
                            "notion_obj_id": page['page_id'],
                            "notion_page_type": page['type'],
                            "tenant_id": current_user.current_tenant_id
                        },
                        document_model=args['doc_form']
                    )
                    extract_settings.append(extract_setting)
        else:
            raise ValueError('Data source type not support')
        indexing_runner = IndexingRunner()
        try:
            response = indexing_runner.indexing_estimate(current_user.current_tenant_id, extract_settings,
                                                         args['process_rule'], args['doc_form'],
                                                         args['doc_language'], args['dataset_id'],
                                                         args['indexing_technique'])
        except LLMBadRequestError:
            raise ProviderNotInitializeError(
                "No Embedding Model available. Please configure a valid provider "
                "in the Settings -> Model Provider.")
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)

        return response, 200
    

class RAGDocumentBatchIndexingStatusApi(Resource):
    @setup_required
    @kaas_login_required
    def get(self, dataset_id, batch):
        # tenant_id = str(current_user.current_tenant_id)
        dataset_id = str(dataset_id)
        batch = str(batch)
        documents = DocumentService.get_batch_documents(dataset_id, batch)
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
    
# 知识库列表,创建知识库
api.add_resource(DatasetListApi,"/dataset")
# .编辑知识库,获取知识库详情
api.add_resource(RAGDatasetApi, "/datasets/<uuid:dataset_id>")
# 获取知识库绑定机器人列表
api.add_resource(RAGDatasetRelatedAppListApi, "/datasets/<uuid:dataset_id>/related-apps")
# 知识库分段预览
api.add_resource(DatasetIndexingEstimateApi, '/datasets/indexing-estimate')
# 获取文件生成进度
api.add_resource(
    RAGDocumentBatchIndexingStatusApi,
    "/datasets/<uuid:dataset_id>/batch/<string:batch>/indexing-status",
)