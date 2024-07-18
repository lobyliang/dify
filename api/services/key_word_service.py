# 用于根据问题选择合适的App或者机器人
import re
from flask import current_app
from sqlalchemy import distinct, text
from controllers.service_api.app.error import (
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from core.errors.error import (
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.rag.retrieval.dc_retrieval.custom_dataset_retrieval import (
    CustomDataSetRetrieval,
)
from models.model import App
from models.account import Account
from models.dataset import AppDatasetJoin, Dataset
from models.dc_models import DocKeyWords, DocKeyWordsClosure
from extensions.ext_database import db
from services.dataset_service import DatasetService, DocumentService
from services.file_service import FileService
from tasks.create_key_words_index_task import key_word_indexing_task
import logging


class KeyWordService:

    @staticmethod
    def AddKeyWord(tenant_id, key_words: list, creator: str, ancestor_id: str):

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
                ancestor_key_word = (
                    db.session.query(DocKeyWords)
                    .filter_by(id=ancestor_id)
                    .one_or_none()
                )
                if ancestor_key_word:
                    domain = ancestor_key_word.domain
                else:
                    # return jsonify(code=400, message='ancestor_id is not exist')
                    raise Exception("ancestor_id is not exist")

            for key_word in key_words:
                if domain:
                    this_domain = domain
                else:
                    this_domain = key_word.get("key_word", None)
                key_word_obj = DocKeyWords(
                    key_word=key_word["key_word"],
                    category=key_word.get("category", None),
                    created_by=creator,
                    tenant_id=tenant_id,
                    domain=this_domain,
                )
                key_words_list.append(key_word_obj)
                db.session.add(key_word_obj)
            db.session.commit()
            if ancestor_id:
                ancestor_closure = (
                    db.session.query(DocKeyWordsClosure)
                    .filter(DocKeyWordsClosure.descendant_id == ancestor_id)
                    .one_or_none()
                )
                depth = 0
                if ancestor_closure:
                    depth = ancestor_closure.depth + 1
                for key_word in key_words_list:
                    key_word_obj = DocKeyWordsClosure(
                        ancestor_id=ancestor_id,
                        descendant_id=key_word.id,
                        tenant_id=tenant_id,
                        depth=depth,
                    )
                    db.session.add(key_word_obj)
                db.session.commit()

            return True
        except Exception as e:
            db.session.rollback()
            logging.error(e)
            raise e

    @staticmethod
    def GetAllLeafs(tenant_id, ancestor_id: str):
        query = text(
            """
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
        """
        )
        result = db.session.execute(
            query, {"parent_id": ancestor_id, "tenant_id": tenant_id}
        )

        # 获取查询结果
        # leaf_nodes = [row['descendant_id'] for row in result]
        return [row for row in result]

    @staticmethod
    def GetKeyWord(tenant_id, ancestor_id: str):
        try:
            if ancestor_id == "None":
                top_level_ancestor_ids = db.session.query(
                    distinct(DocKeyWordsClosure.ancestor_id)
                ).filter(
                    DocKeyWordsClosure.tenant_id == tenant_id
                    and DocKeyWordsClosure.depth == 0
                )

                top_level_key_words = (
                    db.session.query(DocKeyWords)
                    .filter(
                        DocKeyWords.tenant_id == tenant_id
                        and DocKeyWords.id.in_(top_level_ancestor_ids)
                    )
                    .all()
                )
                return 0, parent, top_level_key_words

            parent = (
                db.session.query(DocKeyWords)
                .filter(DocKeyWords.id == ancestor_id)
                .one_or_none()
            )
            if not parent:
                raise ValueError("ancestor_id is not exist")
            depth = (
                db.session.query(DocKeyWordsClosure.depth)
                .filter(DocKeyWordsClosure.descendant_id == ancestor_id)
                .first()
            )
            if depth:
                depth = depth[0] + 2
            else:
                depth = 1
            # ancestor_closure_ids = db.session.query(DocKeyWordsClosure.descendant_id).filter(DocKeyWordsClosure.ancestor_id == ancestor_id).all()
            top_level_ancestor_ids = db.session.query(
                distinct(DocKeyWordsClosure.descendant_id)
            ).filter(DocKeyWordsClosure.ancestor_id == ancestor_id)
            key_words = (
                db.session.query(DocKeyWords)
                .filter(DocKeyWords.id.in_(top_level_ancestor_ids))
                .all()
            )
            return depth, parent, key_words
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def MarhKeyWords(
        paragraphs: list,
        tenant_id: str,
        ancestor_id: str,
        score_threshold=0.2,
        top_n=10,
    ):
        ret = {}
        try:
            depth, parent, key_words = KeyWordService.GetKeyWord(tenant_id, ancestor_id)
            model_manager = ModelManager()
            rerank_model = model_manager.get_default_model_instance(
                tenant_id, ModelType.RERANK
            )
            if rerank_model is None:
                raise Exception("rerank model is not exist")

            for paragraph in paragraphs:
                lines = re.split(r"[\n。;；]", paragraph)
                lines = [li for li in lines if li != ""]
                if len(lines) == 0:
                    continue
                for line in lines:
                    rerank_result = rerank_model.invoke_rerank(
                        line,
                        [
                            (key_word.category + "/" if key_word.category else "")
                            + key_word.key_word
                            for key_word in key_words
                        ],
                        score_threshold=score_threshold,
                        top_n=top_n,
                    )
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    for doc in rerank_result.docs:
                        if doc.text in ret:
                            ret[doc.text]["total_score"] += doc.score
                            ret[doc.text]["count"] += 1
                            if ret[doc.text]["max_score"] < doc.score:
                                ret[doc.text]["max_score"] = doc.score
                        else:
                            ret[doc.text] = {
                                "total_score": doc.score,
                                "count": 1,
                                "max_score": doc.score,
                                "text": doc.text,
                            }

            return ret
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def GetKeyWords(tenant_id: str, key_word: str, domain: str):
        try:
            query = db.session.query(DocKeyWords).filter(
                DocKeyWords.tenant_id == tenant_id, DocKeyWords.key_word == key_word
            )
            if domain:
                query = query.filter(DocKeyWords.domain == domain)
            key_word = query.all()
            if not key_word:
                raise ValueError("key_word is not exist")
            return key_word
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def GetDomainRoot(tenant_id: str, domain: str):
        try:
            domain_root = (
                db.session.query(DocKeyWords)
                .filter(
                    DocKeyWords.tenant_id == tenant_id,
                    DocKeyWords.key_word == domain,
                    DocKeyWords.domain == domain,
                )
                .one_or_none()
            )
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
    def getDataSetByDomain(tenant_id: str, ancestor_id: str):
        try:
            # root = KeyWordService.GetDomainRoot(tenant_id,ancestor_id)
            root = (
                db.session.query(DocKeyWords)
                .filter(
                    DocKeyWords.tenant_id == tenant_id, DocKeyWords.id == ancestor_id
                )
                .one_or_none()
            )
            if not root:
                return None
            return (
                db.session.query(Dataset)
                .filter(
                    Dataset.tenant_id == tenant_id,
                    Dataset.name == KeyWordService.getDefaultDataSetName(root.key_word),
                )
                .one_or_none()
            )
        except Exception as e:
            logging.error(e)
        return None

    @staticmethod
    def getDefaultDataSetName(domain: str):
        return f"《{domain}》关键字知识库"

    @staticmethod
    def BuildKeyWordsRAG(
        tenant_id: str,
        domain: str,
        prefix: str,
        suffix: str,
        account: Account,
        top_k: int = 10,
        score_threshold: float = 0.4,
        rebuild: bool = False,
    ) -> None:
        try:
            root_id = KeyWordService.GetDomainRoot(tenant_id, domain)
            if root_id is None:
                return
            # leafs = KeyWordService.GetAllLeafs(tenant_id,root_id)
            name = KeyWordService.getDefaultDataSetName(domain)
            description = f"存储了关于《{domain}》的关键字知识库"
            dataset = (
                db.session.query(Dataset)
                .filter(Dataset.tenant_id == tenant_id, Dataset.name == name)
                .one_or_none()
            )
            if dataset and rebuild:
                app_joins = AppDatasetJoin.query.filter_by(dataset_id=dataset.id).all()
                if app_joins:
                    app_ids = [app_join.app_id for app_join in app_joins]
                    apps = db.session.query(App).filter(App.id.in_(app_ids)).all()
                    return {
                        "apps": [app.to_dict() for app in apps],
                        "msg": "dataset is exist",
                    }, 400
                DatasetService.delete_dataset(dataset.id, account)
            dataset = DatasetService.create_empty_dataset(
                tenant_id, name, "high_quality", account
            )
            dataset.description = description
            db.session.flush()
            rules = DatasetService.get_process_rules(dataset.id)
            upload_file = FileService.upload_text(text="  ", text_name=name)
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
                        "file_info_list": {"file_ids": [upload_file.id]},
                    },
                },
                "indexing_technique": "high_quality",
                "process_rule": {"rules": {}, "mode": "automatic"},
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
                    "score_threshold": score_threshold,
                },
            }

            if not dataset.indexing_technique and not args["indexing_technique"]:
                raise ValueError("indexing_technique is required.")

            # validate args
            DocumentService.document_create_args_validate(args)

            try:
                documents, batch = DocumentService.save_document_with_dataset_id(
                    dataset, args, account
                )

                leafs = KeyWordService.GetAllLeafs(tenant_id, root_id)
                key_word_indexing_task.dely(
                    tenant_id, dataset.id, documents[0].id, root_id, prefix, suffix
                )
                # for keyword in leafs:
                #     arg={
                #     "content": f"{prefix}{keyword.category}/{keyword.key_word}{suffix}",
                #     "answer": keyword.key_word if not keyword.category else f"{keyword.category}-{keyword.key_word}",
                #     "keywords": [
                #         keyword.key_word,keyword.category
                #     ]
                #     }
                #     SegmentService.create_segment(arg,documents[0],dataset)
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)
            except QuotaExceededError:
                raise ProviderQuotaExceededError()
            except ModelCurrentlyNotSupportError:
                raise ProviderModelCurrentlyNotSupportError()
            return dataset, documents[0], len(leafs)
            # return {
            #     'dataset':dataset,
            #     'documents': documents,
            #     'count':len(leafs)
            # }
        except Exception as e:
            logging.error(e)
            raise e

    # 匹配关键字提示词
    # # 角色
    # - 将给定简历匹配到<keywords>标签中的可选关键字
    # - 给每个匹配到的关键字打个分，取值0~100分
    # - 直接给出关键字和得分，不要进行评价和说明
    # - 只能从<keywords>标签中选择关键字
    # # 格式要求
    # 关键字:分值
    # # 可选关键字
    # <keywords>
    # 后端开发/java开发
    # 后端开发/.net开发
    # 后端开发/大数据开发
    # </keywords>
    # # 简历
    # ● 熟练使用 Java 语言开发，具有良好的编码规范\n● 熟悉基于 SSM、SpringBoot 框架开发\n● 熟悉 Mysql、Oracle 数据库\n● 熟练使用 IDEA、Git、PostMan、PLSQL、Maven 等开发工具\n● 熟悉 Linux 系统日志排查、文件操作等常用命令\n● 了解 SpringCloud、Dubbo ，以及 Redis、RabbitMQ、Zookeeper 的中间件使用\n● 了解 HTML、CSS、Js、Ajax、Freemarker、Vue\n● 了解 JIRA、SVN 的使用\n● 了解基于 Activiti 工作流开发\n工作经历\n杭州财人汇网络股份有限公司武汉分公司 Java 2021.07-2022.12\n1.根据项目立项情况，参与需求评审，结合项目需求提出开发建议，会后整理评审结果，制定开发计划，确立项目开发实施\n方案，并制定相应的开发文档。\n2.根据开发文档，独立负责项目中后端接口的开发，制定接口文档，设计数据库表字段及相应索引，结合接口文档完成接口\n开发及自测工作。\n3.联调前端及其他业务部门，并实时跟进业务开发进度。\n4,配合测试部门完成测试及上线工作，对测试提出的问题进行相应的修改。\n5.负责生产环境遇到的问题进行排查定位，并进行修复升级。\n项目经历\n企业版网掌厅 Java开发 2021.07-2022.12\n项目使用的技术：SpringBoot、SpringCloud、Dubbo、Redis、ActiveMQ、MyBatisPlus、Gradle、Activiti、Oracle\n开发工具：IDEA、Git、PLSQL、PostMan、Xshell、Xftp、SVN.\n项目简介：该项目采用前后端分离的分布式架构开发，主要是为已开户的客户提供证券业务办理。\n项目主要分为4 大模块：柜台模块、业务模块、工作流模块、后台管理模块，柜台接口服务模块和工作流模块是服务提供\n方，业务模块是服务的消费方，采用 Dubbo 进行远程调用，项目开发环境使用了 Nacos 做服务的注册中心和配置中心,使\n用 mq 实现短信的功能的实现，使用 redis 分布式锁解决生产上手机信息修改和基本信息修改流程并发调用修改接口导致\n修改重置的问题。\n1. 柜台模块主要对接各个券商的柜台系统，对接各个券商的柜台系统是通过自定义配置和自定义注解的方式通过反射使对\n接柜台接口的调用统一化处理。\n2. 业务产品模块主要是对业务功能的具体实现。\n3. 工作流模块主要是工作流核心代码实现以及业务相关的工作流程配置文件开发。\n4. 后台模块主要用于流程文件的编写，短信发送信息查看，排查生产问题相关信息的获取，视频认证，协议模板的设置\n等，该项目的主要作用用于券商方面的后台管理，权限检查等网上购物 Java开发 2021.01-2021.06\n该项目是一个综合性平台，类似京东商城，天猫商城。用户可在该系统查看商品，添加购物车，以及在购物车进行付款，\n管理员，运营可以在平台后台管理系统中管理商品，订单等。客服可以在后台管理系统中处理用户的询问以及投诉.\n使用的技术有 Spring,springMVC,Mybatis等.其中控制层采用 springMVC 框架开发；业务逻辑层封装业务流程,为适应业\n务的变更,每一业务模块均有专门的接口及实现类.\n利用 Spring的 IOC 功能将实现类注入到容器中；数据访问层借助于 mybatis 实现,代码简洁，适应不同的数据库.事务部分\n利用 Spring 的声明式事务管理.同时使用 http 协议传递 json 数据方式实现.这样及降低了系统之间的耦合度,又提高了系统\n的扩展性。为了提高系统的性能使用 redis 做某一些业务的缓存（点赞，购物车信息）.\n该项目主要包括以下模块：\n● 后台管理系统：管理商品，订单，类目，商品规格属性，用户管理等功能。\n● 前台系统：用户可以在前台系统中进行注册，登录，浏览商品，下单等操作。\n● 购物车系统：用户可以在首页目录发现中意的商品可添加至购物车，企业可进行清空，删除，付款等功能。\n● 订单系统：提供下单，查询订单，修改订单状态，定时处理订单。\n● 搜索系统：提供商品价格的搜索功能。
    @staticmethod
    def MarhAllKeyWords(
        paragraphs: list,
        tenant_id: str,
        user_id: str,
        ancestor_id: str,
        score_threshold=0.2,
        top_n=10,
        debug=True,
    ):
        ret = {}
        try:
            # key_words = KeyWordService.GetAllLeafs(tenant_id,ancestor_id)
            app_id = current_app.config["DREAM_KEY_WORD_APP_UUID"]
            dataset = KeyWordService.getDataSetByDomain(tenant_id, ancestor_id)
            if not dataset:
                raise Exception("dataset not found")
            # model_manager = ModelManager()
            # rerank_model = model_manager.get_default_model_instance(tenant_id, ModelType.RERANK)
            # if rerank_model is None:
            #     raise Exception("rerank model is not exist")
            custom_dataset_retrieval = CustomDataSetRetrieval()
            for paragraph in paragraphs:
                lines = re.split(r"[\n。;；]", paragraph)
                lines = [li for li in lines if li != ""]
                if len(lines) == 0:
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
                        invoke_from="service-api",
                        show_retrieve_source=False,
                        tenant_id=tenant_id,
                        top_k=top_n,
                        score_threshold=score_threshold,
                        hit_callback=None,
                        reranking_enable=False,
                    )
                    # rerank_result = rerank_model.invoke_rerank(line,[(key_word.category+"/" if key_word.category else '')+key_word.key_word for key_word in key_words],score_threshold=score_threshold,top_n=top_n)
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    if "items" not in results:
                        continue
                    for doc in results["items"]:
                        keyword = doc["content"]["answer"]
                        if keyword in ret:
                            ret[keyword]["total_score"] += doc["score"]
                            ret[keyword]["count"] += 1
                            if ret[keyword]["max_score"] < doc["score"]:
                                ret[keyword]["max_score"] = doc["score"]
                            if debug:
                                ret[keyword]["lines"].append(f"[{doc['score']}]{line}")
                        else:
                            ret[keyword] = {
                                "total_score": doc["score"],
                                "count": 1,
                                "max_score": doc["score"],
                                "text": keyword,
                                "lines": [f"[{doc['score']}]{line}"] if debug else None,
                            }

            return ret
        except Exception as e:
            logging.error(e)
            raise e

    @staticmethod
    def MarhAllKeyWordsByReRank(
        paragraphs: list,
        tenant_id: str,
        ancestor_id: str,
        score_threshold=0.2,
        top_n=10,
        debug=True,
    ):
        ret = {}
        try:
            key_words = KeyWordService.GetAllLeafs(tenant_id, ancestor_id)
            model_manager = ModelManager()
            rerank_model = model_manager.get_default_model_instance(
                tenant_id, ModelType.RERANK
            )
            if rerank_model is None:
                raise Exception("rerank model is not exist")

            for paragraph in paragraphs:
                lines = re.split(r"[\n。;；]", paragraph)
                lines = [li for li in lines if li != ""]
                if len(lines) == 0:
                    continue
                for line in lines:
                    rerank_result = rerank_model.invoke_rerank(
                        line,
                        [
                            (key_word.category + "/" if key_word.category else "")
                            + key_word.key_word
                            for key_word in key_words
                        ],
                        score_threshold=score_threshold,
                        top_n=top_n,
                    )
                    # rerank_result = KeyWordService.MarhKeyWords(line,tenant_id,ancestor_id,score_threshold,top_n)
                    for doc in rerank_result.docs:
                        if doc.text in ret:
                            ret[doc.text]["total_score"] += doc.score
                            ret[doc.text]["count"] += 1
                            if ret[doc.text]["max_score"] < doc.score:
                                ret[doc.text]["max_score"] = doc.score
                            if debug:
                                ret[doc.text]["lines"].append(line)
                        else:
                            ret[doc.text] = {
                                "total_score": doc.score,
                                "count": 1,
                                "max_score": doc.score,
                                "text": doc.text,
                                "lines": [line] if debug else None,
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
