import logging
import time

import click
from celery import shared_task

from extensions.ext_database import db
from models.dataset import Dataset, Document
from services.dataset_service import SegmentService

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
@shared_task(queue='dataset')
def key_word_indexing_task(tenant_id: str,dataset_id:str,document_id:str,root_id: str,prefix:str,suffix:str):
    """
    Async process document
    :param dataset_id:
    :param document_ids:
    :param root_id: 关键词根节点id
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
        from services.key_word_service import KeyWordService
        leafs = KeyWordService.GetAllLeafs(tenant_id,root_id)
        for keyword in leafs:
            arg={
            "content": f"{prefix}{keyword.category}/{keyword.key_word}{suffix}",
            "answer": keyword.key_word if not keyword.category else f"{keyword.category}-{keyword.key_word}",
            "keywords": [
                keyword.key_word,keyword.category
            ]
            }
            SegmentService.create_segment(arg,document,dataset)
        logging.info(click.style(f"{len(leafs)} keywords indexed", fg='green'))
    except Exception as e:
        logging.info(click.style(str(e), fg='yellow'))
        return
