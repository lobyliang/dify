

import logging
from flask_restful import reqparse
from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource
from services.question_service import QuestionService
from flask_restful import marshal,fields
class CreateAppQuestionApi(DatasetApiResource):

    def post(self,tenant_id,app_id):
        argparser = reqparse.RequestParser()
        argparser.add_argument('questions', type=list, required=True,location='json')
        # argparser.add_argument('tenant_id', type=str, required=True,location='json')
        argparser.add_argument('is_virtual', type=bool, required=False, default=False,location='json')
        args = argparser.parse_args(strict=True)
        questions = args['questions']
        # tenant_id = args['tenant_id']
        is_virtual = args['is_virtual']
        
        try:
            documents_ids = QuestionService.add_question(app_id,questions,tenant_id,is_virtual)
            return documents_ids,200
        except Exception as e:
            logging.error(f"创建APP问题失败！for{e}")
            return {}, 200
    
AppQuestionField={
    'id': fields.String,
    'app_id': fields.String,
    'questions': fields.String,
    'status': fields.String,
    'created_at': fields.String,
    'is_virtual': fields.Boolean,
}
# MachedKeyWordsFields={
#     fields.List(fields.Nested(MachedKeyWordsField), attribute="items")
# }
class GetAppQuestionApi(DatasetApiResource):

    def delete(self,tenant_id):
        try:
            argparser = reqparse.RequestParser()
            argparser.add_argument('doc_ids', type=list, required=True,location='json')
            argparser.add_argument('app_id', type=str, required=False,location='json')
            args = argparser.parse_args(strict=True)
            doc_ids = args['doc_ids']
            app_id = args['app_id']
            QuestionService.delete_app_question(tenant_id,doc_ids,app_id)
            return {},200
        except Exception as e:
            logging.error(f"删除APP问题失败！for{e}")
            return {}, 500

    def post(self,tenant_id:str):
        argparser = reqparse.RequestParser()
        argparser.add_argument('app_id', type=str,default=None, required=False,location='json')
        # argparser.add_argument('tenant_id', type=str, required=True,location='json')
        argparser.add_argument('status', type=str,default=None, required=False,location='json')
        argparser.add_argument('page_no', type=int, default=None,required=False,location='json')
        argparser.add_argument('page_size', type=int,default=None, required=False,location='json')
        args = argparser.parse_args()#strict=True
        app_id = args['app_id']
        # tenant_id = args['tenant_id']
        status = args['status']
        page_no = args['page_no']
        page_size = args['page_size']
        try:
            documents_ids,count = QuestionService.get_app_questions(tenant_id,app_id,status,page_no,page_size)
            # return Response(json.dumps([doc.to_dict() for doc in documents_ids]),status=200)
            return {
                "items": marshal(documents_ids,AppQuestionField), #json.dumps([doc.to_dict() for doc in documents_ids]),
                "size": len(documents_ids),
                "page": page_no,
                "pageSize": page_size,
                "total": count,
                "hasMore": ((page_no-1) * page_size+ len(documents_ids) )< count if page_no is not None and page_size is not None else False,

            },200
        except Exception as e:
            logging.error(f"查询APP问题失败！for{e}")
            return [], 500
        
class MarchAppQuestionApi(DatasetApiResource):
    #tenant_id:str,query:str,top_k:int=20,score_threshold:float=0.3
    def post(self,tenant_id:str):
        argparser = reqparse.RequestParser()
        argparser.add_argument('query', type=str, required=True)
        argparser.add_argument('top_k', type=int, required=False, default=20)
        argparser.add_argument('score_threshold', type=float, required=False, default=0.3)
        argparser.add_argument('preprocessing', type=bool, required=False)
        args = argparser.parse_args()
        return QuestionService.march_app_question(tenant_id, args['query'], args['top_k'], args['score_threshold'],args['preprocessing'])
    
api.add_resource(CreateAppQuestionApi, '/appQuestion/<string:app_id>/create')    
api.add_resource(GetAppQuestionApi, '/appQuestion/list') 
api.add_resource(MarchAppQuestionApi, '/appQuestion/march')