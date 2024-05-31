import threading
from typing import Optional, cast

from exceptiongroup import catch
from flask import Flask, current_app
from sympy import true

from core import model_manager
from core.app.app_config.entities import DatasetEntity, DatasetRetrieveConfigEntity
from core.app.entities.app_invoke_entities import InvokeFrom, ModelConfigWithCredentialsEntity
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.entities.agent_entities import PlanningStrategy
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance, ModelManager
from core.model_runtime.entities.message_entities import PromptMessageTool
from core.model_runtime.entities.model_entities import ModelFeature, ModelType
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.models.document import Document
from core.rag.retrieval.router.multi_dataset_function_call_router import FunctionCallMultiDatasetRouter
from core.rag.retrieval.router.multi_dataset_react_route import ReactMultiDatasetRouter
from core.rerank.rerank import RerankRunner
from core.tools.tool.dataset_retriever.dataset_multi_retriever_tool import DatasetMultiRetrieverTool
from core.tools.tool.dataset_retriever.dataset_retriever_base_tool import DatasetRetrieverBaseTool
from core.tools.tool.dataset_retriever.dataset_retriever_tool import DatasetRetrieverTool
from extensions.ext_database import db
from models.account import Tenant
from models.dataset import Dataset, DatasetQuery, DocumentSegment
from models.dataset import Document as DatasetDocument
from services.file_service import FileService

default_retrieval_model = {
    'search_method': 'semantic_search',
    'reranking_enable': False,
    'reranking_model': {
        'reranking_provider_name': '',
        'reranking_model_name': ''
    },
    'top_k': 2,
    'score_threshold_enabled': False
}

muitiple_retrieval_config = {
  "retrieval_model": "multiple",
  "top_k": 3,
  "score_threshold": 0.5,
  "score_threshold_enabled": True,
  "reranking_model": {
    "reranking_provider_name": "xinference",
    "reranking_model_name": "beg-reranker-large"
  },
  "datasets": {
    "datasets": [
      {
        "dataset": {
          "enabled": True,
          "id": "c734797d-6bb1-4132-8089-8310be994de3"
        },
        "dataset": {
          "enabled": True,
          "id": "c734797d-6bb1-4132-8089-8310be994de3"
        }
      }
    ]
  }
}

single_retrieval_config = {
  "retrieval_model": "single",
  "datasets": {
    "datasets": [
      {
        "dataset": {
          "enabled": True,
          "id": "c734797d-6bb1-4132-8089-8310be994de3"
        },
        "dataset": {
          "enabled": True,
          "id": "c734797d-6bb1-4132-8089-8310be994de3"
        }
      }
    ]
  }
}

class CustomDataSetRetrieval:
    model_manager = model_manager.ModelManager()
    reranking_model_name = None
    reranking_provider_name = None
    tenant_count = None
    default_tenant = None
    
    # default_rerank_model = model_manager.get_default_model_instance(ModelType.RERANKER)
    
    def get_datasets(sef,tanent_id):
        ret = []
        try:
            datasets = db.session.query(Dataset).filter(Dataset.tenant_id == tanent_id).all()
            for ds in datasets:
                item = {}
                ds_docs = db.session.query(DatasetDocument).filter(DatasetDocument.dataset_id == ds.id and DatasetDocument.indexing_status=='completed' and DatasetDocument.enabled==True).all()
                # ds_docs = db.session.query(DatasetDocument).filter(DatasetDocument.dataset_id == ds.id and DatasetDocument.indexing_status=='completed' and DatasetDocument.enabled==True\
                #                                                    and DatasetDocument.doc_metadata['author'].astext=='rouyi租户ID').all()
                item['id'] = ds.id
                item['name'] = ds.name
                item['description']=ds.description
                item['retrieval_model']=ds.retrieval_model
                item['docs'] = []
                for doc in ds_docs:
                    doc_item={}
                    doc_item['id'] = doc.id
                    doc_item['name'] = doc.name
                    doc_item['word_count'] = doc.word_count
                    doc_item['data_source'] = doc.data_source_info_dict
                    doc_item['doc_form'] = doc.doc_form
                    doc_item['language'] = doc.doc_language
                    item['docs'].append(doc_item)
                ret.append(item)
        except Exception as e:
            raise ValueError('数据库查询失败！',e)
        return ret

    def retrieval(self,user_id: str, 
                
                #  model_config: ModelConfigWithCredentialsEntity,
                #  config: DatasetEntity,
                 app_id:str,# 用于关联查询请求，统计查询请求
                 retrieve_strategy:str,
                 search_method:str,
                 dataset_ids: list[str],
                 reorgenazie_output:bool,# 是否重新组织输出文本：是否用大模型
                 query: str,
                 invoke_from: InvokeFrom,
                 show_retrieve_source: bool,
                 hit_callback: DatasetIndexToolCallbackHandler,
                 tenant_id: Optional[str]=None,
                 top_k: Optional[int] = None,
                 score_threshold: Optional[float] = None,
                 reranking_model: Optional[dict] = None) -> Optional[str]:
        if not CustomDataSetRetrieval.tenant_count:
            CustomDataSetRetrieval.tenant_count =  db.session.query(Tenant).count()
        if not CustomDataSetRetrieval.default_tenant:
            CustomDataSetRetrieval.default_tenant= db.session.query(Tenant).first()
        if len(dataset_ids) == 0:
                    return None
        retrieve_strategy = DatasetRetrieveConfigEntity.RetrieveStrategy.value_of(retrieve_strategy)
        if search_method not in ['keyword_search','semantic_search','full_text_search','hybrid_search']:
               raise ValueError(f'invalid search_method value {search_method}')
        
        user_from = 'account' if invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end_user'

        if not tenant_id and CustomDataSetRetrieval.tenant_count==1:
            tenant_id = CustomDataSetRetrieval.default_tenant.id
        else:
              raise ValueError(f'租户ID必须为非空字符串')
        
        # 如果没有调用模式配置，则不需要重新组织语言并调用大模型
        planning_strategy = None
        
        # check model is support tool calling
        model_instance = CustomDataSetRetrieval.model_manager.get_default_model_instance(tenant_id,ModelType.LLM)

        # get model schema
        model_schema = model_instance.model_type_instance.get_model_schema(
            model=model_instance.model,
            credentials=model_instance.credentials
        )

        if not model_schema:
            return None

        planning_strategy = PlanningStrategy.REACT_ROUTER
        features = model_schema.features
        if features:
            if ModelFeature.TOOL_CALL in features \
                    or ModelFeature.MULTI_TOOL_CALL in features:
                planning_strategy = PlanningStrategy.ROUTER

        model_config = ModelConfigWithCredentialsEntity(
            provider=model_instance.provider,
            model=model_instance.model,
            model_schema=model_schema,
            credentials=model_instance.credentials,
            provider_model_bundle=model_instance.provider_model_bundle)

        available_datasets = []
        for dataset_id in dataset_ids:
            # get dataset from dataset id
            dataset = db.session.query(Dataset).filter(
                Dataset.tenant_id == tenant_id,
                Dataset.id == dataset_id
            ).first()

            # pass if dataset is not available
            if not dataset:
                continue

            # pass if dataset is not available
            if (dataset and dataset.available_document_count == 0
                    and dataset.available_document_count == 0):
                continue

            available_datasets.append(dataset)

        all_documents = []
        if retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE:
            all_documents = self.single_retrieve(app_id, tenant_id, user_id, user_from, available_datasets, query,
                                                 model_instance,
                                                 model_config, planning_strategy)
        elif retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE:
            if not CustomDataSetRetrieval.reranking_model_name:
                default_rerank = CustomDataSetRetrieval.model_manager.get_default_model_instance(tenant_id=tenant_id,model_type=ModelType.RERANK)
                if default_rerank:
                    CustomDataSetRetrieval.reranking_model_name = default_rerank.model
                    CustomDataSetRetrieval.reranking_provider_name = default_rerank.provider    
                else:
                    raise ValueError('系统默认排序模型未配置')
            all_documents = self.multiple_retrieve(app_id, tenant_id, user_id, user_from,
                                                   available_datasets, query, top_k,
                                                   score_threshold,
                                                   CustomDataSetRetrieval.reranking_provider_name,
                                                   CustomDataSetRetrieval.reranking_model_name)
            
        document_score_list = {}
        for item in all_documents:
            if item.metadata.get('score'):
                document_score_list[item.metadata['doc_id']] = item.metadata['score']

        document_context_list = []
        index_node_ids = [document.metadata['doc_id'] for document in all_documents]
        segments = DocumentSegment.query.filter(
            DocumentSegment.dataset_id.in_(dataset_ids),
            DocumentSegment.completed_at.isnot(None),
            DocumentSegment.status == 'completed',
            DocumentSegment.enabled == True,
            DocumentSegment.index_node_id.in_(index_node_ids)
        ).all()
        context_list = []
        if segments:
            index_node_id_to_position = {id: position for position, id in enumerate(index_node_ids)}
            sorted_segments = sorted(segments,
                                     key=lambda segment: index_node_id_to_position.get(segment.index_node_id,
                                                                                       float('inf')))
            resource_number = 1
            for segment in sorted_segments:
                if segment.answer:
                    content = f'question:{segment.content} answer:{segment.answer}'
                else:
                    conetent = segment.content
                doc_res = {'No':resource_number,'content':content,'score': document_score_list.get(segment.index_node_id, None),'seg_id':segment.id}
                doc_res['attach_files'] = FileService.get_chunck_attach_files_info(segment.id)
                if show_retrieve_source:
                    # for segment in sorted_segments:
                    dataset = Dataset.query.filter_by(
                        id=segment.dataset_id).first()
                    document = DatasetDocument.query.filter(DatasetDocument.id == segment.document_id,
                                                            DatasetDocument.enabled == True,
                                                            DatasetDocument.archived == False,
                                                            ).first()
                    if dataset and document:
                        doc_res['source']={
                            'dataset_id': dataset.id,
                            'dataset_name': dataset.name,
                            'document_id': document.id,
                            'document_name': document.name,
                            'data_source_type': document.data_source_type,
                            'segment_id': segment.id,
                            'retriever_from': invoke_from.to_source(),
                            'hit_count' : segment.hit_count,
                            'word_count' : segment.word_count
                            
                        }
                        source = {
                            'position': resource_number,
                            'dataset_id': dataset.id,
                            'dataset_name': dataset.name,
                            'document_id': document.id,
                            'document_name': document.name,
                            'data_source_type': document.data_source_type,
                            'segment_id': segment.id,
                            'retriever_from': invoke_from.to_source(),
                            'score': document_score_list.get(segment.index_node_id, None)
                        }

                        if invoke_from.to_source() == 'dev':
                            source['hit_count'] = segment.hit_count
                            source['word_count'] = segment.word_count
                            source['segment_position'] = segment.position
                            source['index_node_hash'] = segment.index_node_hash
                        if segment.answer:
                            source['content'] = f'question:{segment.content} \nanswer:{segment.answer}'
                        else:
                            source['content'] = segment.content
                        context_list.append(source)
                resource_number += 1
                document_context_list.append(doc_res)
            if hit_callback:
                hit_callback.return_retriever_resource_info(context_list)
                    
            return str("\n".join(document_context_list))
        return ''
    def single_retrieve(self, app_id: str,
                    tenant_id: str,
                    user_id: str,
                    user_from: str,
                    available_datasets: list,
                    query: str,
                    model_instance: ModelInstance,
                    model_config: ModelConfigWithCredentialsEntity,
                    planning_strategy: PlanningStrategy,
                    ):
        tools = []
        for dataset in available_datasets:
            description = dataset.description
            if not description:
                description = 'useful for when you want to answer queries about the ' + dataset.name

            description = description.replace('\n', '').replace('\r', '')
            message_tool = PromptMessageTool(
                name=dataset.id,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            )
            tools.append(message_tool)
        dataset_id = None
        if planning_strategy == PlanningStrategy.REACT_ROUTER:
            react_multi_dataset_router = ReactMultiDatasetRouter()
            dataset_id = react_multi_dataset_router.invoke(query, tools, model_config, model_instance,
                                                            user_id, tenant_id)

        elif planning_strategy == PlanningStrategy.ROUTER:
            function_call_router = FunctionCallMultiDatasetRouter()
            dataset_id = function_call_router.invoke(query, tools, model_config, model_instance)

        if dataset_id:
            # get retrieval model config
            dataset = db.session.query(Dataset).filter(
                Dataset.id == dataset_id
            ).first()
            if dataset:
                retrieval_model_config = dataset.retrieval_model \
                    if dataset.retrieval_model else default_retrieval_model

                # get top k
                top_k = retrieval_model_config['top_k']
                # get retrieval method
                if dataset.indexing_technique == "economy":
                    retrival_method = 'keyword_search'
                else:
                    retrival_method = retrieval_model_config['search_method']
                # get reranking model
                reranking_model = retrieval_model_config['reranking_model'] \
                    if retrieval_model_config['reranking_enable'] else None
                # get score threshold
                score_threshold = .0
                score_threshold_enabled = retrieval_model_config.get("score_threshold_enabled")
                if score_threshold_enabled:
                    score_threshold = retrieval_model_config.get("score_threshold")

                results = RetrievalService.retrieve(retrival_method=retrival_method, dataset_id=dataset.id,
                                                    query=query,
                                                    top_k=top_k, score_threshold=score_threshold,
                                                    reranking_model=reranking_model)
                self._on_query(query, [dataset_id], app_id, user_from, user_id)
                if results:
                    self._on_retrival_end(results)
                return results
        return []
    

    def _on_query(self, query: str, dataset_ids: list[str], app_id: str, user_from: str, user_id: str) -> None:
        """
        Handle query.
        """
        if not query:
            return
        for dataset_id in dataset_ids:
            dataset_query = DatasetQuery(
                dataset_id=dataset_id,
                content=query,
                source='app',
                source_app_id=app_id,
                created_by_role=user_from,
                created_by=user_id
            )
            db.session.add(dataset_query)
        db.session.commit()    


    def multiple_retrieve(self,
                          app_id: str,
                          tenant_id: str,
                          user_id: str,
                          user_from: str,
                          available_datasets: list,
                          query: str,
                          top_k: int,
                          score_threshold: float,
                          reranking_provider_name: str,
                          reranking_model_name: str):
        threads = []
        all_documents = []
        dataset_ids = [dataset.id for dataset in available_datasets]
        for dataset in available_datasets:
            retrieval_thread = threading.Thread(target=self._retriever, kwargs={
                'flask_app': current_app._get_current_object(),
                'dataset_id': dataset.id,
                'query': query,
                'top_k': top_k,
                'all_documents': all_documents,
            })
            threads.append(retrieval_thread)
            retrieval_thread.start()
        for thread in threads:
            thread.join()
        # do rerank for searched documents
        model_manager = ModelManager()
        rerank_model_instance = model_manager.get_model_instance(
            tenant_id=tenant_id,
            provider=reranking_provider_name,
            model_type=ModelType.RERANK,
            model=reranking_model_name
        )

        rerank_runner = RerankRunner(rerank_model_instance)
        all_documents = rerank_runner.run(query, all_documents,
                                          score_threshold,
                                          top_k)
        self._on_query(query, dataset_ids, app_id, user_from, user_id)
        if all_documents:
            self._on_retrival_end(all_documents)
        return all_documents


    def _on_retrival_end(self, documents: list[Document]) -> None:
        """Handle retrival end."""
        for document in documents:
            query = db.session.query(DocumentSegment).filter(
                DocumentSegment.index_node_id == document.metadata['doc_id']
            )

            # if 'dataset_id' in document.metadata:
            if 'dataset_id' in document.metadata:
                query = query.filter(DocumentSegment.dataset_id == document.metadata['dataset_id'])

            # add hit count to document segment
            query.update(
                {DocumentSegment.hit_count: DocumentSegment.hit_count + 1},
                synchronize_session=False
            )

            db.session.commit()            


    def _retriever(self, flask_app: Flask, dataset_id: str, query: str, top_k: int, all_documents: list):
        with flask_app.app_context():
            dataset = db.session.query(Dataset).filter(
                Dataset.id == dataset_id
            ).first()

            if not dataset:
                return []

            # get retrieval model , if the model is not setting , using default
            retrieval_model = dataset.retrieval_model if dataset.retrieval_model else default_retrieval_model

            if dataset.indexing_technique == "economy":
                # use keyword table query
                documents = RetrievalService.retrieve(retrival_method='keyword_search',
                                                      dataset_id=dataset.id,
                                                      query=query,
                                                      top_k=top_k
                                                      )
                if documents:
                    all_documents.extend(documents)
            else:
                if top_k > 0:
                    # retrieval source
                    documents = RetrievalService.retrieve(retrival_method=retrieval_model['search_method'],
                                                          dataset_id=dataset.id,
                                                          query=query,
                                                          top_k=top_k,
                                                          score_threshold=retrieval_model['score_threshold']
                                                          if retrieval_model['score_threshold_enabled'] else None,
                                                          reranking_model=retrieval_model['reranking_model']
                                                          if retrieval_model['reranking_enable'] else None
                                                          )

                    all_documents.extend(documents)            