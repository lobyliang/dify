

import argparse
from array import array
from dataclasses import asdict
import logging
from flask_restful import Resource
from flask import Response, json, jsonify, request
from flask_restful import Resource, marshal, reqparse
from controllers.service_api.app.error import ProviderNotInitializeError
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.indexing_runner import IndexingRunner
from core.rag.extractor.entity.extract_setting import ExtractSetting
from models.account import Account,TenantAccountJoin
from models.dc_models import DocKeyWords, DocKeyWordsClosure
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

class AddKeyWordApi(DatasetApiResource):
    def post(self, tenant_id):
        parser = reqparse.RequestParser()
        parser.add_argument('key_words', type=list[dict], required=True, help='key_word is required')
        parser.add_argument('ancestor_id', type=str, required=False)
        parser.add_argument('creator', type=str, required=False)
        args = parser.parse_args()
        ancestor_id = args.get('ancestor_id')
        key_words = args.get('key_words')
        ancestor_key_word = None
        domain = None
        key_words_list = []
        try:
            if ancestor_id:
                ancestor_key_word = db.session.query(DocKeyWords).filter_by(id=ancestor_id).one_or_none()
            if ancestor_key_word:
                domain = ancestor_key_word.domain
            else:
                return jsonify(code=400, message='ancestor_id is not exist')
            for key_word in key_words:
                key_word_obj = DocKeyWords(key_word=key_word["key_word"],\
                                        category=key_word["category"],\
                                            tenant_id=tenant_id,domain=domain)
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
                                            depth=depth)
                    db.session.add(key_word_obj)
                db.session.commit()
            
            return jsonify(code=200, message='success')
        except Exception as e:
            db.session.rollback()
            logging.error(e)
            return jsonify(code=500, message=str(e))



# api.add_resource(CreateAppQuestionApi, '/appQuestion/<string:app_id>/create')    
# api.add_resource(GetAppQuestionApi, '/appQuestion/list') 
# api.add_resource(MarchAppQuestionApi, '/appQuestion/<string:tenant_id>/march')