
import uuid
from controllers.service_api.wraps import DatasetApiResource
from core.rag.retrieval.custom_dataset_retrieval import CustomDataSetRetrieval
from controllers.service_api import api
from flask_restful import marshal, reqparse

from models.dataset import Dataset


class RAGQueryApi(DatasetApiResource):
    def get(self, tenant_id, ):
        parser = reqparse.RequestParser()
        parser.add_argument('user_id', type=str, required=True, nullable=False, location='json')
        parser.add_argument('app_id', type=str, required=True, nullable=False, location='json')
        parser.add_argument('retrieve_strategy', type=str,choices=['single','multiple'], required=True, nullable=False, location='json')
        parser.add_argument('search_method', type=str,choices=['keyword_search','semantic_search','full_text_search','hybrid_search'], required=True, nullable=False, location='json')
        parser.add_argument('dataset_ids', type=list, required=True, nullable=False, location='json')
        parser.add_argument('reorgenaize', type=bool, default=True, required=True, nullable=False,
                            location='json')
        parser.add_argument('query', type=str, choices=Dataset.INDEXING_TECHNIQUE_LIST, nullable=False,
                            location='json')
        parser.add_argument('show_source', type=bool, required=True, nullable=False,
                            location='json')
        args = parser.parse_args()
        user_id = args['user_id']
        app_id = args['app_id']
        retrieve_strategy = args['retrieve_strategy']
        search_method = args['search_method']
        dataset_ids = args['dataset_ids']
        reorgenaize = args['reorgenaize']
        query = args['query']
        show_source = args['show_source']
        # get dataset
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return custom_dataset_retrieval.retrieval(
            user_id=user_id,
            app_id=app_id,
            retrieve_strategy=retrieve_strategy,
            search_method=search_method,
            dataset_ids=dataset_ids,
            reorgenazie_output=reorgenaize,
            query=query,
            invoke_from='service-api',
            show_retrieve_source=show_source,
            tenant_id=tenant_id,
        ),200
    
class RAGDataSetListApi(DatasetApiResource):
    def get(self, tenant_id, ):
        custom_dataset_retrieval = CustomDataSetRetrieval()
        return custom_dataset_retrieval.get_datasets(tenant_id),200
    

api.add_resource(RAGQueryApi, '/rag/query')    
api.add_resource(RAGDataSetListApi, '/rag/list')