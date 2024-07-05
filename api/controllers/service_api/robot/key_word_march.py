

import logging
from flask import jsonify
from flask_restful import marshal,fields, reqparse
from fields import dataset_fields
from fields import document_fields
from libs.helper import TimestampField
from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource
from fields.dataset_fields import dataset_fields
from libs.login import current_user
from fields.document_fields import (
    document_fields
)
from services.key_word_service import KeyWordService
def parse_list_of_dicts(value):
    try:
        return value
    except Exception as e:
        raise ValueError('Invalid list of dictionaries'+{e})
    
class AddKeyWordApi(DatasetApiResource):
    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        # parser.add_argument('key_words', type=list,action='append',required=True, help='key_word is required')
        parser.add_argument('key_words', type=parse_list_of_dicts,required=True,location='json', help='key_word is required')
        parser.add_argument('ancestor_id', type=str, required=False)
        parser.add_argument('creator', type=str, required=False)
        args = parser.parse_args()
        ancestor_id = args.get('ancestor_id')
        key_words = args.get('key_words')
        creator = args.get('creator')
        try:
            KeyWordService.AddKeyWord(tenant_id,key_words,creator,ancestor_id)
            return jsonify(code=200, message="success")
        except Exception as e:
            logging.error(e)
            return jsonify(code=500, message=str(e))
        
DocKeyWordFields={
    'id': fields.String,
    'key_word': fields.String,
    'category': fields.String,
    'domain': fields.String,
    'created_by': fields.String,
    'created_at': TimestampField,
    'tenant_id': fields.String,
}
DocKeyWordsFields={
    fields.List(fields.Nested(DocKeyWordFields), attribute="items")
}

MachedKeyWordsField={
    'index': fields.Integer,
    'text': fields.String,
    'score': fields.Float,
}
MachedKeyWordsFields={
    fields.List(fields.Nested(MachedKeyWordsField), attribute="items")
}
class GetKeyWordsApi(DatasetApiResource):        
    def get(self, tenant_id,ancestor_id:str):

        try:
            depth,parent,key_words = KeyWordService.GetKeyWord(tenant_id,ancestor_id)
        except Exception as e:
            logging.error(e)
            return jsonify(code=500, message=str(e))
        return {"depth":depth,"parent":marshal(parent,DocKeyWordFields),"keywords":marshal(key_words,DocKeyWordFields)},200


    def post(self, tenant_id,ancestor_id:str):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('paragraph', type=list,location='json',required=True, help='Paragraph is required')
            parser.add_argument('score_threshold', type=float,location='json',required=False, help='score_threshold is required')
            parser.add_argument('top_n', type=int,location='json',required=False, help='top_n is required')
            parser.add_argument('debug', type=bool,location='json',required=False, help='显示命中的是那一句话')
            args = parser.parse_args()
            paragraphs = args.get('paragraph')
            score_threshold = args.get('score_threshold')
            top_n = args.get('top_n')
            isDebug = args.get('debug')
            ret = {}
            
            if len(paragraphs)==0:
                return jsonify(code=200, message="success",data=[])
        
            # ret = KeyWordService.MarhKeyWords(paragraphs,tenant_id,ancestor_id,score_threshold,top_n)
            ret2 = KeyWordService.MarhAllKeyWords(paragraphs,tenant_id,current_user.id,ancestor_id,score_threshold,top_n,isDebug)
            ret2 = sorted(ret2.items(), key=lambda x: (x[1]['total_score'],x[1]['max_score']), reverse=True)
            return ret2
        except Exception as e:
            logging.error(e)
            return jsonify(code=500, message=str(e))
    
class GetKeyWordsByTagApi(DatasetApiResource):        
    def get(self, tenant_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('domain', type=str,location='args',required=False, help='domain of the key word')
            parser.add_argument('keyword', type=str,location='args',required=True, help='domain of the key word')
            args = parser.parse_args()
            domain = args.get('domain')
            key_word = args.get('keyword')
            key_words = KeyWordService.GetKeyWords(tenant_id,key_word,domain)
            return marshal(key_words,DocKeyWordFields),200
        except Exception as e:
            logging.error(e)
            return jsonify(code=500, message=str(e))
        
class BuildKeyWordsRAGApi(DatasetApiResource):
    def post(self,tenant_id): 
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('prefix', type=str, required=True)
            parser.add_argument('suffix', type=str, required=True)
            parser.add_argument('domain', type=str, required=True)
            parser.add_argument('top_k', type=int, required=False)
            parser.add_argument('score_threshold', type=int, required=False)
            parser.add_argument('rebuild', type=bool, required=False,default=False)
            args = parser.parse_args()
            domain = args.get('domain')
            prefix = args.get('prefix')
            suffix = args.get('suffix')
            top_k = args.get('top_k')
            rebuild = args.get('rebuild')

            score_threshold = args.get('score_threshold')
            dataset,document,count = KeyWordService.BuildKeyWordsRAG(tenant_id,domain,prefix,suffix,current_user,top_k,score_threshold,rebuild)
            return {'dataset':marshal(dataset,dataset_fields),'document':marshal(document,document_fields),'count':count}
        except Exception as e:    
            logging.error(e)
            return {'message':str(e)},500

api.add_resource(AddKeyWordApi, '/keywords')  
api.add_resource(GetKeyWordsByTagApi, '/keywords/search')  
api.add_resource(GetKeyWordsApi, '/keywords/<string:ancestor_id>') 
api.add_resource(BuildKeyWordsRAGApi, '/keywords/build') 
# api.add_resource(GetAppQuestionApi, '/appQuestion/list') 
# api.add_resource(MarchAppQuestionApi, '/appQuestion/<string:tenant_id>/march')