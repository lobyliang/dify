

import argparse
from array import array
from dataclasses import asdict
from flask_restful import Resource
from flask import Response, json, request
from flask_restful import Resource, marshal, reqparse
from controllers.service_api.app.error import ProviderNotInitializeError
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.indexing_runner import IndexingRunner
from core.rag.extractor.entity.extract_setting import ExtractSetting
from models.account import Account,TenantAccountJoin
import services
import services.dataset_service
from extensions.ext_database import db
from services.dataset_service import DatasetService, DocumentService
from models.model import  UploadFile
from controllers.service_api import api
from controllers.service_api.dataset.error import  DocumentAlreadyFinishedError
from controllers.service_api.wraps import DatasetApiResource
from fields.dataset_fields import dataset_query_detail_fields
from libs.login import current_user
from models.dataset import Dataset, DatasetProcessRule, Document, DocumentSegment
from services.dataset_service import DatasetService
from werkzeug.exceptions import Forbidden, NotFound
from fields.document_fields import (
    document_status_fields,
)
from services.question_service import QuestionService

class CreateAppQuestionApi(Resource):

    def post(self, app_id):
        argparser = reqparse.RequestParser()
        argparser.add_argument('questions', type=list, required=True,location='json')
        argparser.add_argument('tenant_id', type=str, required=True,location='json')
        argparser.add_argument('is_virtual', type=bool, required=False, default=False,location='json')
        args = argparser.parse_args(strict=True)
        questions = args['questions']
        tenant_id = args['tenant_id']
        is_virtual = args['is_virtual']
        
        try:
            documents_ids = QuestionService.add_question(app_id,questions,tenant_id,is_virtual)
            return documents_ids,200
        except Exception as e:
            raise e
        
        return {}, 200
    
class GetAppQuestionApi(Resource):

    def get(self):
        argparser = reqparse.RequestParser()
        argparser.add_argument('app_id', type=str, required=False,location='json')
        argparser.add_argument('tenant_id', type=str, required=True,location='json')
        argparser.add_argument('status', type=str, required=False,location='json')
        args = argparser.parse_args(strict=True)
        app_id = args['app_id']
        tenant_id = args['tenant_id']
        status = args['status']
        try:
            documents_ids = QuestionService.get_app_questions(tenant_id,app_id,status)
            return Response(json.dumps([doc.to_dict() for doc in documents_ids]),status=200)
        except Exception as e:
            raise e
        
        return [], 200
        
class MarchAppQuestionApi(Resource):
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
api.add_resource(MarchAppQuestionApi, '/appQuestion/<string:tenant_id>/march')