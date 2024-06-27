import threading
from typing import Optional

from flask import Flask, current_app

from core import model_manager
from core.app.app_config.entities import DatasetRetrieveConfigEntity
from core.app.entities.app_invoke_entities import InvokeFrom, ModelConfigWithCredentialsEntity
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.entities.agent_entities import PlanningStrategy
from core.model_manager import ModelInstance, ModelManager
from core.model_runtime.entities.message_entities import PromptMessageRole, PromptMessageTool
from core.model_runtime.entities.model_entities import ModelFeature, ModelType
from core.prompt.advanced_prompt_transform import AdvancedPromptTransform
from core.prompt.entities.advanced_prompt_entities import ChatModelMessage, CompletionModelPromptTemplate
from core.prompt.simple_prompt_transform import ModelMode
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.models.document import Document
from core.rag.rerank.rerank import RerankRunner
from core.rag.retrieval.router.multi_dataset_function_call_router import FunctionCallMultiDatasetRouter
from core.rag.retrieval.router.multi_dataset_react_route import ReactMultiDatasetRouter
# from core.rerank.rerank import RerankRunner
from extensions.ext_database import db
from models.account import Tenant
from models.dataset import Dataset, DatasetQuery, DocumentSegment
from models.dataset import Document as DatasetDocument
from models.model import EndUser
from services.file_info_service import FileInfoService


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
    @staticmethod
    def get_end_user(user_id:str,app_id:str,tenant_id:str):

        if not user_id:
            user_id = 'DEFAULT-USER'

        end_user = db.session.query(EndUser) \
            .filter(
            EndUser.tenant_id == tenant_id,
            EndUser.app_id == app_id,
            EndUser.session_id == user_id,
            EndUser.type == 'service_api'
        ).first()

        if end_user is None:
            end_user = EndUser(
                tenant_id=tenant_id,
                app_id=app_id,
                type='service_api',
                is_anonymous=True if user_id == 'DEFAULT-USER' else False,
                session_id=user_id,
                external_user_id=user_id
            )
            db.session.add(end_user)
            db.session.commit()

        return end_user
    
    # default_rerank_model = model_manager.get_default_model_instance(ModelType.RERANKER)

    def get_chuncks_by_order(self,doc_id,page_size,page_number):
        if page_number<1:
            page_number=1
        if page_size<1:
            page_size=10
        docs = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == doc_id)\
            .order_by(DocumentSegment.hit_count.desc()).order_by(DocumentSegment.created_at.desc())\
            .offset((page_number-1)*page_size)\
            .limit(page_size).all()

        return docs
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
    def reorgenazie_output(self,model_config:ModelConfigWithCredentialsEntity,model_instance:ModelInstance,query:str,answer:str):

        if not answer:
            return None
        if not model_instance:
            return None
        prompt_messages = []
        system_prompt=f'# 角色\n你是一个智能问答助手，你将根据用户的问题，使用知识库中的知识，回答用户的问题。\n- 根据对知识库内容中答案的理解回答问题\n- 要注意区分答案中的不同概率\n- 简要使用中文回答\n# 知识库\n知识库中包含以下内容：\n---\n{answer}---\n'
        user_prompt=f'# 用户\n用户问题：{query}'
        if model_config.mode== ModelMode.CHAT.value:
            system_prompt_messages = ChatModelMessage(
                role=PromptMessageRole.SYSTEM,
                text=system_prompt
            )
            prompt_messages.append(system_prompt_messages)
            user_prompt_message = ChatModelMessage(
                role=PromptMessageRole.USER,
                text=user_prompt
            )
            prompt_messages.append(user_prompt_message)
        elif model_config.mode== ModelMode.COMPLETION.value:
            completion_prompt= CompletionModelPromptTemplate(
                text=system_prompt+user_prompt,
            )
            prompt_messages.append(completion_prompt)

        prompt_transform = AdvancedPromptTransform()
        prompt_messages = prompt_transform.get_prompt(
            prompt_template=prompt_messages,
            inputs={},
            query='',
            files=[],
            context='',
            memory_config=None,
            memory=None,
            model_config=model_config
        )
        result = model_instance.invoke_llm(prompt_messages,model_config.parameters,tools=None,stop=None,stream=False)
        return result.message.content
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
                #  reranking_model: Optional[dict] = None
                 ) -> Optional[str]:
        if not CustomDataSetRetrieval.tenant_count:
            CustomDataSetRetrieval.tenant_count =  db.session.query(Tenant).count()
        if not CustomDataSetRetrieval.default_tenant:
            CustomDataSetRetrieval.default_tenant= db.session.query(Tenant).first()
        if not CustomDataSetRetrieval.reranking_model_name:
            default_rerank = CustomDataSetRetrieval.model_manager.get_default_model_instance(tenant_id=tenant_id,model_type=ModelType.RERANK)
            if default_rerank:
                CustomDataSetRetrieval.reranking_model_name = default_rerank.model
                CustomDataSetRetrieval.reranking_provider_name = default_rerank.provider    
            else:
                raise ValueError('系统默认排序模型未配置')
        retrieval_model_config ={ 'search_method':search_method,\
                                  'top_k':top_k,\
                                  'score_threshold':score_threshold,
                                  'score_threshold_enabled':score_threshold is not None,
                                  'reranking_enable':True,
                                   'reranking_model': {
                                 'reranking_provider_name':CustomDataSetRetrieval.reranking_provider_name,
                                    'reranking_model_name': CustomDataSetRetrieval.reranking_model_name,
                                    },
                                 }
        if len(dataset_ids) == 0:
                    return None
        retrieve_strategy = DatasetRetrieveConfigEntity.RetrieveStrategy.value_of(retrieve_strategy)
        if search_method not in ['keyword_search','semantic_search','full_text_search','hybrid_search']:
               raise ValueError(f'invalid search_method value {search_method}')
        
        user_from = 'account' if invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end_user'

        if not tenant_id:
            if CustomDataSetRetrieval.tenant_count==1:
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

        model_mode= model_instance.model_type_instance.get_model_mode(
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
            mode=model_mode.value,
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

        if len(available_datasets)==0:
            return {"msg":"没有找到对应的知识库"}

        all_documents = []
        if retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE:
            all_documents,query_id = self.single_retrieve(app_id, tenant_id, user_id, user_from, available_datasets, query,
                                                 model_instance,
                                                 model_config, planning_strategy,retrieval_model_config)
        elif retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE:
            all_documents,query_id = self.multiple_retrieve(app_id, tenant_id, user_id, user_from,
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
                answer = ''
                if segment.answer:
                    content = {'question':segment.content, 'answer':segment.answer}
                    answer = segment.answer
                else:
                    content = {'answer':segment.content}
                    answer = segment.content
                if reorgenazie_output:
                    content['AI_answer'] = self.reorgenazie_output(model_config,model_instance,query,answer)
                
                doc_res = {'No':resource_number,'content':content,'score': document_score_list.get(segment.index_node_id, None),'seg_id':segment.id}
                doc_res['attach_files'] = FileInfoService.get_chunck_attach_files_info(segment.id)
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
                            'retriever_from': invoke_from,
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
                            'retriever_from': invoke_from,
                            'score': document_score_list.get(segment.index_node_id, None)
                        }

                        if invoke_from == 'dev':
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
                    
            return {"query_id":query_id,"items": document_context_list}
        return {"query_id":query_id,"items": []}
    def single_retrieve(self, app_id: str,
                    tenant_id: str,
                    user_id: str,
                    user_from: str,
                    available_datasets: list,
                    query: str,
                    model_instance: ModelInstance,
                    model_config: ModelConfigWithCredentialsEntity,
                    planning_strategy: PlanningStrategy,
                    retrieval_model_config:dict,
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
                # retrieval_model_config = dataset.retrieval_model \
                #     if dataset.retrieval_model else default_retrieval_model

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
                endUser = CustomDataSetRetrieval.get_end_user(user_id=user_id,tenant_id= tenant_id,app_id=app_id)
                
                query_id = self._on_query(query, [dataset_id], app_id, user_from, endUser.id)
                if results:
                    self._on_retrival_end(results)
                return results,query_id
        return [],None
    

    def _on_query(self, query: str, dataset_ids: list[str], app_id: str, user_from: str, user_id: str) -> None:
        """
        Handle query.
        """
        if not query and dataset_ids and len(dataset_ids)>0:
            return None
        
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
        return dataset_query.id


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
        endUser = CustomDataSetRetrieval.get_end_user(user_id=user_id,tenant_id= tenant_id,app_id=app_id)
                
        query_id = self._on_query(query, dataset_ids, app_id, user_from, endUser.id)
        if all_documents:
            self._on_retrival_end(all_documents)
        return all_documents,query_id


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

    @staticmethod
    def comment_rag_query(query_id:str,like:int):
        is_like = 1 if like == 1 else 0
        is_dislike = 1 if like == 0 else 0
        rag_query = db.session.query(DatasetQuery).filter(
            DatasetQuery.id == query_id
        ).first()
        if not rag_query:
            raise ValueError("query not found")
        rag_query.like = rag_query.like + is_like,
        rag_query.dislike=rag_query.dislike + is_dislike
        db.session.commit()
        return {"like":rag_query.like,"dislike":rag_query.dislike}
