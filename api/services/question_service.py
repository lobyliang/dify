
# 用于根据问题选择合适的App或者机器人
from flask import json
from core.model_manager import ModelManager
from core.model_runtime.entities.message_entities import SystemPromptMessage, UserPromptMessage
from core.model_runtime.entities.model_entities import ModelType
from core.rag.datasource.vdb.dc_vector_factory import DCVector
from core.rag.models.document import Document
from models import model
from models.dc_models import AppQuestions
from extensions.ext_database import db
from tasks.dc_add_app_question_index_task import dc_add_app_question_index_task
import logging

def next_name(name:str):
    for i in range(len(name)):
        char = chr(ord(name[i]) + 1)
        if char > 'z':
            char = 'a'
        name = name.replace(name[i], char)
    return name

class QuestionService:
    @staticmethod
    def add_question(app_id: str, questions: list[str], tenant_id: str,is_virtual: bool = False) -> None:
        """
        添加问题
        :param app_id:
        :param questions:
        :param tenant_id:
        :return:
        """
        try:
            all_questions = []
            for question in questions:
                app_questions = AppQuestions(app_id=app_id, questions=question, tenant_id=tenant_id,status='indexing',is_virtual=is_virtual)
                one_query = QuestionService.get_one_app_questions(app_id=app_id,query=question,tenant_id=tenant_id)
                if not one_query:
                    all_questions.append(app_questions)
                    db.session.add(app_questions)
                elif one_query.status=='indexing':
                    all_questions.append(one_query)
                else:
                    logging.warning(f'{app_id} : {question} 已经索引完成，无需再次索引')
            if len(all_questions)>0:
                db.session.commit()
                documents_ids = [question.id for question in all_questions]
                dc_add_app_question_index_task.delay(documents_ids,tenant_id,app_id)
            return [str(doc_id) for doc_id in  documents_ids],len(all_questions)
        except Exception as e:
            logging.exception(f"App问题索引任务 failed:{e}")

        return [],0
    
    @staticmethod
    def get_app_questions(tenant_id:str,app_id:str=None,status:str=None) -> list[AppQuestions]:
        """
        Get all app questions
        :param tenant_id:
        :param app_id:
        :return:
        """
        try:
            query = db.session.query(AppQuestions).filter(AppQuestions.tenant_id==tenant_id)
            if app_id:
                query = query.filter(AppQuestions.app_id==app_id)
            
            if status:
                query = query.filter(AppQuestions.status==status)
            app_questions =query.all()
            return app_questions
        except Exception as e:
            logging.exception(f"查询App问题 failed:{e}")        
        return []
        
    @staticmethod
    def get_one_app_questions(tenant_id:str,app_id:str,query:str) -> AppQuestions:
        """
        Get all app questions
        :param tenant_id:
        :param app_id:
        :return:
        """
        try:
            app_question =db.session.query(AppQuestions).filter(AppQuestions.tenant_id==tenant_id,AppQuestions.app_id==app_id,AppQuestions.questions==query).one_or_none()
            return app_question
        except Exception as e:
            logging.exception(f"查询App问题 failed:{e}")        
        return None 
    
    @staticmethod
    def march_app_question(tenant_id:str,query:str,top_k:int=20,score_threshold:float=0.3,preprocessing:bool=False):
        """
        匹配App问题
        :param tenant_id:租户id
        :param query:问题
        :return:匹配到的APP统计数量
        """
        #score_threshold
        #top_k
        # karg = {"top_k":top_k,"score_threshold":score_threshold}
        if preprocessing:
            model_manager = ModelManager()
            llm_model = model_manager.get_default_model_instance(tenant_id, ModelType.LLM)
            prompts = [SystemPromptMessage(content="列出问句中的姓名和部门。严禁添加任何额外说明，仅返回格式要求内容。\n输出格式{\"姓名\":[],\"部门\":[]}"),
            UserPromptMessage(content=query)]
            ret = llm_model.invoke_llm(prompt_messages=prompts,stream=False)
            if ret and ret.message:
                json_str = ret.message.content
                try:
                    json_obj = json.loads(json_str)
                    if "姓名" in json_obj :
                        x_name = 'XXX'
                        for name in json_obj["姓名"]:
                            query=query.replace(name,x_name)
                            x_name = next_name(x_name)
                    if "部门" in json_obj:
                        x_name = 'xxx'
                        for depart in json_obj["部门"]:
                            query= query.replace(depart,x_name)
                            x_name = next_name(x_name)
                except Exception as e:
                    logging.error(f"json.loads error:{e}")
            
        vector = DCVector(tenant_id=tenant_id)
         #metadata = {"app_id": app_id,"tenant_id": tenant_id}
        docs:list[Document] = vector.search_by_vector(query,top_k=top_k,score_threshold=score_threshold)
        ret = {"marched_app_id":None,"march_list":{}}
        max_score_app_id = ""
        max_score = 0
        max_count_app_id = None
        max_count = 0
        recommend = 0
        if docs:
            for doc in docs:
                app_id = doc.metadata["app_id"]
                if app_id in ret['march_list']:
                    ret["march_list"][app_id]['count']+=1
                    ret["march_list"][app_id]['total_score']+=doc.metadata["score"]
                    ret["march_list"][app_id]['avg_score']=ret["march_list"][app_id]['total_score']\
                    / ret["march_list"][app_id]['count']
                    if doc.metadata["score"]>ret["march_list"][app_id]['max_score']:
                        ret["march_list"][app_id]['max_score']=doc.metadata["score"]
                else:
                    ret["march_list"][app_id]={"count":1,"max_score":doc.metadata["score"],"total_score":doc.metadata["score"],"avg_score":doc.metadata["score"]}

                if ret["march_list"][app_id]['count']>max_count:
                    max_count = ret["march_list"][app_id]['count']
                    max_count_app_id = app_id
                
                if doc.metadata['score']>max_score:
                    max_score = doc.metadata['score']
                    max_score_app_id = app_id

            
        
            if max_count_app_id != max_score_app_id:
                # 说明判断的结果存在风险
                recommend = 1
                # 如果最大分数的匹配数量不到最大匹配数量的一半，则采用最大数量的匹配APP
                if ret["march_list"][max_score_app_id]/ret["march_list"][max_count_app_id]["count"]<0.5:
                    ret["marched_app_id"] = max_count_app_id
                else:
                    # 先这么处理，具体情况待测试后再调整
                    ret["marched_app_id"] = max_score_app_id

            elif max_count_app_id == max_score_app_id:
                # 说明判断的结果是正确的
                recommend = 2
                if ret["march_list"][max_count_app_id]['count']==ret["march_list"][max_score_app_id]['count']==top_k:
                    recommend = 3
                ret["marched_app_id"] = max_count_app_id
            else:
                # 说明判断的结果是错误的
                recommend = -1

        ret['recommend'] = recommend
        return ret




