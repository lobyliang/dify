import logging
import time

import click
from celery import shared_task

from core.model_manager import ModelManager
from core.model_runtime.entities.message_entities import SystemPromptMessage, UserPromptMessage
from core.model_runtime.entities.model_entities import ModelType
from extensions.ext_database import db
from models.dataset import Dataset, Document


import datetime
import logging
import time
import uuid

from flask_login import current_user
from sqlalchemy import func

from extensions.ext_redis import redis_client
from libs import helper
from models.dataset import (
    Dataset,
    Document,
    DocumentSegment,
)
from services.vector_service import VectorService

# 构建知识库提示词
# # 角色
# 你是一个知识库构建机器人，模仿以下范例，写出“从事后端开发/.NET岗位”
# - 写出一段描述，能高度匹配“从事后端开发/.NET岗位”
# - 用一句话罗列出所有关键信息。不要进行详细说明。

# # 范例
# 从事后端开发/Java岗位，使用SSM、SpringBoot框架开发，采用MySQL，MongoDB数据库，使用IDEA、Git、Gradle、Maven等工具，使用SpringCloud,Dubbo,Redis
# \RabbitMQ ,Zookeeper等中间件。


# 明白了，您需要生成一段文本，用于描述特定的岗位、行业和专业技能，以便在简历匹配过程中进行更精确的关联。以下是一些示例：

# 岗位：
# "作为一个【岗位名称】，您将负责在【行业名称】中关键角色的担任。这包括【关键职责或任务】，并需要精通【相关技能或工具】以应对【行业特定挑战或需求】。"

# 行业：
# "在【行业名称】，您将面对【行业特定挑战或机遇】。这需要深入了解【行业关键概念或趋势】，并且能够应用【相关技能或工具】以推动【行业内的某些活动或目标】。"

# 专业技能：
# "拥有【专业技能名称】将使您能够在【行业名称】中脱颖而出。这些技能包括【具体技能要求或应用场景】，并且是应对【行业挑战或需求】的关键因素之一。"

# 请告诉我具体需要生成哪些内容，我可以根据您的要求进一步调整和完善。
#---------------------岗位提示词---------------
# # 角色
# 你是一个简历编写机器人，模仿以下范例，详细的描述所要求岗位在哪些行业中，从事那些关键职责或任务，并需要精通哪些关键技能和工具，以应对该行业需要完成的工作和任务。
# - 用一句话罗列出所有关键信息。不要进行详细说明。
# - 尽量多的列出所需的技能、工具、职责和任务
# - 只回答一遍
# # 格式要求：
# 作为一个【岗位名称】，我将负责在【行业名称】中关键角色的担任。这包括【关键职责或任务】，并需要精通【相关技能或工具】以应对【行业特定工作任务和需求】。
# # 岗位要求
def generate_key_word_content(tenant_id:str,key_word:str,category:str,prompt:str):
    try:
        model_manager = ModelManager()
        model = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM
        )
        systemPrompt = SystemPromptMessage(content=prompt)
        query_messages = UserPromptMessage(content=key_word if not category else f"{category}/{key_word}")
        result = model.invoke_llm([systemPrompt, query_messages],stream=False)
        return str(result.message.content)

    except Exception as e:
        logging.error(e)
    return None

def create_segment(args: dict,tenant_id:str, document: Document, dataset: Dataset,account_id:str):
        content = args['content']
        doc_id = str(uuid.uuid4())
        segment_hash = helper.generate_text_hash(content)
        tokens = 0
        if dataset.indexing_technique == 'high_quality':
            model_manager = ModelManager()
            embedding_model = model_manager.get_model_instance(
                tenant_id=tenant_id,
                provider=dataset.embedding_model_provider,
                model_type=ModelType.TEXT_EMBEDDING,
                model=dataset.embedding_model
            )
            # calc embedding use tokens
            tokens = embedding_model.get_text_embedding_num_tokens(
                texts=[content]
            )
        lock_name = 'add_segment_lock_document_id_{}'.format(document.id)
        with redis_client.lock(lock_name, timeout=600):
            max_position = db.session.query(func.max(DocumentSegment.position)).filter(
                DocumentSegment.document_id == document.id
            ).scalar()
            segment_document = DocumentSegment(
                tenant_id=tenant_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                index_node_id=doc_id,
                index_node_hash=segment_hash,
                position=max_position + 1 if max_position else 1,
                content=content,
                word_count=len(content),
                tokens=tokens,
                status='completed',
                indexing_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                completed_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                created_by=account_id
            )
            if document.doc_form == 'qa_model':
                segment_document.answer = args['answer']

            db.session.add(segment_document)
            db.session.commit()

            # save vector index
            try:
                VectorService.create_segments_vector([args['keywords']], [segment_document], dataset)
            except Exception as e:
                logging.exception("create segment index failed")
                segment_document.enabled = False
                segment_document.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                segment_document.status = 'error'
                segment_document.error = str(e)
                db.session.commit()
            segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment_document.id).first()
            return segment

@shared_task(queue='dataset')
def key_word_indexing_task(tenant_id: str,dataset_id:str,document_id:str,root_id: str,prefix:str,suffix:str,prompt:str,account_id:str):
    """
    Async process document
    :param dataset_id:
    :param document_ids:
    :param root_id: 关键词根节点id
    :param prefix:
    :param suffix:
    :param prompt:用于创建o搜素内容的提示词
    Usage: key_word_indexing_task.delay(tenant_id,dataset_id, document_id,root_id)
    """

    start_at = time.perf_counter()

    dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()

    # check document limit
    # features = FeatureService.get_features(dataset.tenant_id)
    try:
        dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            logging.warning(click.style(f'dataset {dataset_id} not found',fg='red'))
            return 
        
        document = db.session.query(Document).filter(Document.id==document_id).one_or_none()
        if not document:
            logging.warning(click.style(f'document {document_id} not found',fg='red'))
            return
        from services.dc_key_word_service import KeyWordService
        leafs = KeyWordService.GetAllLeafs(tenant_id,root_id)
        for keyword in leafs:
            if prompt:
                key_word_content = generate_key_word_content(tenant_id,keyword.key_word,keyword.category,prompt)
                time.sleep(10)
            else:
                key_word_content = f"{prefix}{keyword.category}/{keyword.key_word}{suffix}"
            arg={
            "content": key_word_content,
            "answer": keyword.key_word if not keyword.category else f"{keyword.category}-{keyword.key_word}",
            "keywords": [
                keyword.key_word,keyword.category
            ]
            }
            create_segment(arg,tenant_id,document,dataset,account_id)
        logging.info(click.style(f"{len(leafs)} keywords indexed", fg='green'))
    except Exception as e:
        logging.info(click.style(str(e), fg='yellow'))
        return
