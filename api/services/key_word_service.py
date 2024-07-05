
# 用于根据问题选择合适的App或者机器人
import re
import uuid
from flask import current_app, json
from flask_restful import marshal
from pyparsing import Keyword
from sqlalchemy import distinct, text
from controllers.service_api.app.error import ProviderModelCurrentlyNotSupportError, ProviderNotInitializeError, ProviderQuotaExceededError
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_manager import ModelManager
from core.model_runtime.entities.message_entities import SystemPromptMessage, UserPromptMessage
from core.model_runtime.entities.model_entities import ModelType
from core.rag.datasource.vdb.dc_vector_factory import DCVector
from core.rag.models.document import Document
from core.rag.retrieval.dc_retrieval.custom_dataset_retrieval import CustomDataSetRetrieval
from models.model import App
from models.account import Account
from models.dataset import AppDatasetJoin, Dataset
from models.dc_models import AppQuestions, DocKeyWords, DocKeyWordsClosure
from extensions.ext_database import db
from services.dataset_service import DatasetService, DocumentService, SegmentService
from services.file_service import FileService
from tasks.dc_add_app_question_index_task import dc_add_app_question_index_task
import logging


class KeyWordService:

    @staticmethod
    def AddKeyWord(tenant_id,key_words:list,creator:str, ancestor_id:str):

        # try:
        #     key_words = json.loads(key_words)
        #     if not isinstance(key_words, list) or not all(isinstance(item, dict) for item in key_words):
        #         return {'message': 'Invalid data format, expected list of dictionaries'}, 400
        # except Exception as e:
        #     return {'message': 'Invalid JSON format'}, 400
        ancestor_key_word = None
        domain = None
        key_words_list = []
        try:
            if ancestor_id:
                ancestor_key_word = db.session.query(DocKeyWords).filter_by(id=ancestor_id).one_or_none()
                if ancestor_key_word:
                    domain = ancestor_key_word.domain
                else:
                    # return jsonify(code=400, message='ancestor_id is not exist')
                    raise Exception('ancestor_id is not exist')

            for key_word in key_words:
                if domain:
                    this_domain = domain
                else:
                    this_domain = key_word.get("key_word",None)
                key_word_obj = DocKeyWords(key_word=key_word["key_word"],\
                                        category=key_word.get("category",None),\
                                        created_by=creator,\
                                        tenant_id=tenant_id,domain=this_domain)
                key_words_list.append(key_word_obj)
                db.session.add(key_word_obj)
            db.session.commit()
            if ancestor_id:
                ancestor_closure = db.session.query(DocKeyWordsClosure).filter(DocKeyWordsClosure.descendant_id == ancestor_id).one_or_none()
                depth=0
                if ancestor_closure:
                    depth = ancestor_closure.depth + 1
                for key_word in key_words_list:
                    key_word_obj = DocKeyWordsClosure(ancestor_id=ancestor_id,\
                                            descendant_id=key_word.id,\
                                            tenant_id=tenant_id,\
                                            depth=depth)
                    db.session.add(key_word_obj)
                db.session.commit()
            
            return True
        except Exception as e:
            db.session.rollback()
            logging.error(e)
            raise e

    @staticmethod
    def GetAllLeafs(tenant_id, ancestor_id:str):
        query=text("""
        select * from key_words where key_words.id in (WITH RECURSIVE descendants AS (
        -- 基础查询，从给定的父节点ID开始
        SELECT 
            kw.id AS descendant_id
        FROM 
            public.key_words kw
        JOIN 
            public.key_words_closure kwc ON kw.id = kwc.descendant_id
        WHERE 
            kwc.ancestor_id = :parent_id -- 将'父节点ID'替换为实际的父节点ID
                     			and
  			kwc.tenant_id = :tenant_id

        UNION ALL

        -- 递归查询，找到所有子节点
        SELECT 
            kw.id AS descendant_id
        FROM 
            public.key_words kw
        JOIN 
            public.key_words_closure kwc ON kw.id = kwc.descendant_id
        JOIN 
            descendants d ON d.descendant_id = kwc.ancestor_id
    )
    SELECT 
        d.descendant_id
    FROM 
        descendants d
    LEFT JOIN 
        public.key_words_closure kwc ON d.descendant_id = kwc.ancestor_id
    WHERE 
        kwc.descendant_id IS NULL)
        """)
        result = db.session.execute(query, {'parent_id': ancestor_id, 'tenant_id': tenant_id})

        # 获取查询结果
        # leaf_nodes = [row['descendant_id'] for row in result]
        return [row for row in result]

    @staticmethod
    def GetKeyWord(tenant_id, ancestor_id:str):
        try:
            if ancestor_id == 'None':
                top_level_ancestor_ids = (
                db.session.query(distinct(DocKeyWordsClosure.ancestor_id))
                .filter(DocKeyWordsClosure.tenant_id==tenant_id and  DocKeyWordsClosure.depth == 0)
                )

                top_level_key_words = (
                    db.session.query(DocKeyWords)
                    .filter(DocKeyWords.tenant_id == tenant_id and DocKeyWords.id.in_(top_level_ancestor_ids))
                    .all()
                )
                return 0,parent,top_level_key_words
                
            
            parent = db.session.query(DocKeyWords).filter(DocKeyWords.id==ancestor_id).one_or_none()
            if not parent:
                raise ValueError("ancestor_id is not exist")
            depth = db.session.query(DocKeyWordsClosure.depth).filter(DocKeyWordsClosure.descendant_id == ancestor_id).first()
            if depth:
                depth = depth[0] + 2
            else:
                depth = 1
            # ancestor_closure_ids = db.session.query(DocKeyWordsClosure.descendant_id).filter(DocKeyWordsClosure.ancestor_id == ancestor_id).all()
            top_level_ancestor_ids = (
                db.session.query(distinct(DocKeyWordsClosure.descendant_id))
                .filter(DocKeyWordsClosure.ancestor_id == ancestor_id)
                )
            key_words = db.session.query(DocKeyWords).filter(DocKeyWords.id.in_(top_level_ancestor_ids)).all()
            return depth,parent,key_words
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def MarhKeyWords(paragraphs:list,tenant_id:str,ancestor_id:str,score_threshold=0.2,top_n=10):
        ret = {}
        try:
            depth,parent,key_words = KeyWordService.GetKeyWord(tenant_id,ancestor_id)
            model_manager = ModelManager()
            rerank_model = model_manager.get_default_model_instance(tenant_id, ModelType.RERANK)
            if rerank_model is None:
                raise Exception("rerank model is not exist")
            
            for paragraph in paragraphs:
                lines = re.split(r'[\n。;；]', paragraph)
                lines = [li for li in lines if li !='']
                if len(lines)==0:
                    continue
                for line in lines:
                    rerank_result = rerank_model.invoke_rerank(line,[(key_word.category+"/" if key_word.category else '')+key_word.key_word for key_word in key_words],score_threshold=score_threshold,top_n=top_n)
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    for doc in rerank_result.docs:
                        if doc.text in ret:
                            ret[doc.text]['total_score']+=doc.score
                            ret[doc.text]['count']+=1
                            if ret[doc.text]['max_score']<doc.score:
                                ret[doc.text]['max_score']=doc.score
                        else:
                            ret[doc.text]={
                                'total_score':doc.score,
                                'count':1,
                                'max_score':doc.score,
                                'text':doc.text
                            }
            
            return ret
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def GetKeyWords(tenant_id:str,key_word:str,domain:str):
        try:
            query = db.session.query(DocKeyWords).filter(DocKeyWords.tenant_id == tenant_id,DocKeyWords.key_word == key_word)
            if domain:
                query = query.filter(DocKeyWords.domain == domain)
            key_word =  query.all()
            if not key_word:
                raise ValueError("key_word is not exist")
            return key_word
        except Exception as e:
            logging.error(e)
            raise e
        
    @staticmethod
    def GetDomainRoot(tenant_id:str,domain:str):
        try:
            domain_root = db.session.query(DocKeyWords).filter(DocKeyWords.tenant_id == tenant_id ,DocKeyWords.key_word == domain , DocKeyWords.domain == domain).one_or_none()
            if not domain_root:
                raise ValueError("domain is not exist")
            return domain_root.id
        except Exception as e:
            logging.error(e)
            raise e
        
    # @staticmethod
    # def BuildKeyWordsRAG(tenant_id: str,  domain: str) -> None:
    #     try:
    #         domain_root = KeyWordService.GetDomainRoot(tenant_id,domain)
    #         KeyWordService.BuildKeyWordsRAG(tenant_id,domain_root)
    #     except Exception as e:
    #         logging.error(e)
    #         raise e
    @staticmethod
    def getDataSetByDomain(tenant_id:str,ancestor_id:str):
        try:
            # root = KeyWordService.GetDomainRoot(tenant_id,ancestor_id)
            root = db.session.query(DocKeyWords).filter(DocKeyWords.tenant_id == tenant_id, DocKeyWords.id == ancestor_id).one_or_none()
            if not root:
                return None
            return db.session.query(Dataset).filter(Dataset.tenant_id == tenant_id,Dataset.name == KeyWordService.getDefaultDataSetName(root.key_word)).one_or_none()
        except Exception as e:
            logging.error(e)
        return None
    
    @staticmethod
    def getDefaultDataSetName(domain: str):
        return f"《{domain}》关键字知识库"
    @staticmethod
    def BuildKeyWordsRAG(tenant_id: str, domain: str,prefix:str,suffix:str, account:Account,top_k:int=10,score_threshold:float=0.4,rebuild:bool=False) -> None:
        try:
            root_id = KeyWordService.GetDomainRoot(tenant_id,domain)
            if root_id is None:
                return
            leafs = KeyWordService.GetAllLeafs(tenant_id,root_id)
            name = KeyWordService.getDefaultDataSetName(domain)
            description = f"存储了关于《{domain}》的关键字知识库"
            dataset = db.session.query(Dataset).filter(Dataset.tenant_id == tenant_id,Dataset.name == name).one_or_none()
            if dataset and rebuild:
                app_joins = AppDatasetJoin.query.filter_by(dataset_id=dataset.id).all()
                if app_joins:
                    app_ids=[app_join.app_id for app_join in app_joins]
                    apps = db.session.query(App).filter(App.id.in_(app_ids)).all()
                    return {"apps":[app.to_dict() for app in apps],"msg":"dataset is exist"},400
                DatasetService.delete_dataset(dataset.id,account)
            dataset = DatasetService.create_empty_dataset(tenant_id,name,'high_quality',account)
            dataset.description = description
            db.session.flush()
            rules = DatasetService.get_process_rules(dataset.id)
            upload_file = FileService.upload_text(text="  ",text_name=name)
            # parser.add_argument('indexing_technique', type=str, choices=Dataset.INDEXING_TECHNIQUE_LIST, nullable=False,
            #                     location='json')
            # parser.add_argument('data_source', type=dict, required=False, location='json')
            # parser.add_argument('process_rule', type=dict, required=False, location='json')
            #             {
            #   "mode": "custom",
            #   "rules": {
            #     "pre_processing_rules": [
            #       {
            #         "id": "remove_extra_spaces",
            #         "enabled": true
            #       },
            #       {
            #         "id": "remove_urls_emails",
            #         "enabled": false
            #       }
            #     ],
            #     "segmentation": {
            #       "delimiter": "\n",
            #       "max_tokens": 500,
            #       "chunk_overlap": 50
            #     }
            #   }
            # }
            # parser.add_argument('duplicate', type=bool, default=True, nullable=False, location='json')
            # parser.add_argument('original_document_id', type=str, required=False, location='json')
            # parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
            # parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
            #                     location='json')
            # parser.add_argument('retrieval_model', type=dict, required=False, nullable=False,
            #                     location='json')
            # args = parser.parse_args()


            # {
            #   "data_source": {
            #     "type": "upload_file",
            #     "info_list": {
            #       "data_source_type": "upload_file",
            #       "file_info_list": {
            #         "file_ids": [
            #           "b89b33f9-401c-4011-87a2-204107e93ecf"
            #         ]
            #       }
            #     }
            #   },
            #   "indexing_technique": "high_quality",
            #   "process_rule": {
            #     "rules": {},
            #     "mode": "automatic"
            #   },
            #   "doc_form": "text_model",
            #   "doc_language": "Chinese",
            #   "retrieval_model": {
            #     "search_method": "semantic_search",
            #     "reranking_enable": true,
            #     "reranking_model": {
            #       "reranking_provider_name": "xinference",
            #       "reranking_model_name": "beg-reranker-large"
            #     },
            #     "top_k": 3,
            #     "score_threshold_enabled": false,
            #     "score_threshold": 0.5
            #   }
            # }

            args = {
              "data_source": {
                "type": "upload_file",
                "info_list": {
                  "data_source_type": "upload_file",
                  "file_info_list": {
                    "file_ids": [
                      upload_file.id
                    ]
                  }
                }
              },
              "indexing_technique": "high_quality",
              "process_rule": {
                "rules": {},
                "mode": "automatic"
              },
              "doc_form": "qa_model",
              "doc_language": "Chinese",
              "retrieval_model": {
                "search_method": "semantic_search",
                "reranking_enable": False,
                "reranking_model": {
                #   "reranking_provider_name": "xinference",
                #   "reranking_model_name": "beg-reranker-large"
                },
                "top_k": top_k,
                "score_threshold_enabled": True,
                "score_threshold": score_threshold
              }
            }

            if not dataset.indexing_technique and not args['indexing_technique']:
                raise ValueError('indexing_technique is required.')

            # validate args
            DocumentService.document_create_args_validate(args)

            try:
                documents, batch = DocumentService.save_document_with_dataset_id(dataset, args, account)
                for keyword in leafs:
                    arg={
                    "content": f"{prefix}{keyword.category}/{keyword.key_word}{suffix}",
                    "answer": keyword.key_word if not keyword.category else f"{keyword.category}-{keyword.key_word}",
                    "keywords": [
                        keyword.key_word,keyword.category
                    ]
                    }
                    SegmentService.create_segment(arg,documents[0],dataset)
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)
            except QuotaExceededError:
                raise ProviderQuotaExceededError()
            except ModelCurrentlyNotSupportError:
                raise ProviderModelCurrentlyNotSupportError()
            return dataset,documents[0],len(leafs)
            # return {
            #     'dataset':dataset,
            #     'documents': documents,
            #     'count':len(leafs) 
            # }    
        except Exception as e:
            logging.error(e)
            raise e
    @staticmethod
    def MarhAllKeyWords(paragraphs:list,tenant_id:str,user_id:str,ancestor_id:str,score_threshold=0.2,top_n=10,debug=True):
        ret = {}
        try:
            # key_words = KeyWordService.GetAllLeafs(tenant_id,ancestor_id)
            app_id = current_app.config['DREAM_KEY_WORD_APP_UUID']
            dataset = KeyWordService.getDataSetByDomain(tenant_id,ancestor_id)
            if not dataset:
                raise Exception("dataset not found")
            # model_manager = ModelManager()
            # rerank_model = model_manager.get_default_model_instance(tenant_id, ModelType.RERANK)
            # if rerank_model is None:
            #     raise Exception("rerank model is not exist")
            custom_dataset_retrieval = CustomDataSetRetrieval()
            for paragraph in paragraphs:
                lines = re.split(r'[\n。;；]', paragraph)
                lines = [li for li in lines if li !='']
                if len(lines)==0:
                    continue
                for line in lines:
                    results = custom_dataset_retrieval.retrieval(
                                                user_id=user_id,
                                                app_id=app_id,
                                                retrieve_strategy="single",
                                                search_method="semantic_search",
                                                dataset_ids=[dataset.id],
                                                reorgenazie_output=False,
                                                query=line,
                                                invoke_from='service-api',
                                                show_retrieve_source=False,
                                                tenant_id=tenant_id,
                                                top_k=top_n,
                                                score_threshold=score_threshold,
                                                hit_callback = None,
                                                reranking_enable=False
                                            )
                    # rerank_result = rerank_model.invoke_rerank(line,[(key_word.category+"/" if key_word.category else '')+key_word.key_word for key_word in key_words],score_threshold=score_threshold,top_n=top_n)
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    if "items" not in results:
                        continue
                    for doc in results["items"]:
                        keyword = doc["content"]["answer"]
                        if keyword in ret:
                            ret[keyword]['total_score']+=doc["score"]
                            ret[keyword]['count']+=1
                            if ret[keyword]['max_score']<doc["score"]:
                                ret[keyword]['max_score']=doc["score"]
                            if debug:
                                ret[keyword]['lines'].append(f"[{doc['score']}]{line}")
                        else:
                            ret[keyword]={
                                'total_score':doc["score"],
                                'count':1,
                                'max_score':doc["score"],
                                'text':keyword,
                                'lines':[f"[{doc['score']}]{line}"] if debug else None
                            }
            
            return ret
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def MarhAllKeyWordsByReRank(paragraphs:list,tenant_id:str,ancestor_id:str,score_threshold=0.2,top_n=10,debug=True):
        ret = {}
        try:
            key_words = KeyWordService.GetAllLeafs(tenant_id,ancestor_id)
            model_manager = ModelManager()
            rerank_model = model_manager.get_default_model_instance(tenant_id, ModelType.RERANK)
            if rerank_model is None:
                raise Exception("rerank model is not exist")
            
            for paragraph in paragraphs:
                lines = re.split(r'[\n。;；]', paragraph)
                lines = [li for li in lines if li !='']
                if len(lines)==0:
                    continue
                for line in lines:
                    rerank_result = rerank_model.invoke_rerank(line,[(key_word.category+"/" if key_word.category else '')+key_word.key_word for key_word in key_words],score_threshold=score_threshold,top_n=top_n)
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    for doc in rerank_result.docs:
                        if doc.text in ret:
                            ret[doc.text]['total_score']+=doc.score
                            ret[doc.text]['count']+=1
                            if ret[doc.text]['max_score']<doc.score:
                                ret[doc.text]['max_score']=doc.score
                            if debug:
                                ret[doc.text]['lines'].append(line)
                        else:
                            ret[doc.text]={
                                'total_score':doc.score,
                                'count':1,
                                'max_score':doc.score,
                                'text':doc.text,
                                'lines':[line] if debug else None
                            }
            
            return ret
        except Exception as e:
            logging.error(e)
            raise e
        
    # @staticmethod
    # def Preprocess(tenant_id, query):
    #     model_manager = ModelManager()
    #     embedding_model = model_manager.get_default_model_instance(tenant_id, ModelType.TEXT_EMBEDDING)
    #     if embedding_model is None:
    #         return None
        
    #     query_embedding = embedding_model.invoke_rerank()