from email.policy import default
from flask_login import current_user
import logging
from flask_restful import Resource, marshal, marshal_with, reqparse
from controllers.console.setup import setup_required
from libs.login import kaas_login_required
from controllers.kaas_api import api
from services.dc_dict_service import DictService
from extensions.ext_database import db
from werkzeug.exceptions import BadRequest
from flask_restful import Resource, fields, marshal_with
from werkzeug.exceptions import NotFound

class DirBindingApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    def put(self,category_type:str, category_id:int):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "target_ids",
            type=list,
            nullable=False,
            location="json",
        )

        args = parser.parse_args()
        target_ids = args["target_ids"]
        if not target_ids:
            raise BadRequest("target_ids is required")
        ret = []
        try:
            for target_id in target_ids:
                binding = DictService.add_category_binding(category_id,target_id,category_type,current_user.id)
                ret.append(binding.id)
            return {"acmount":len(ret),"binding_ids":ret}, 200
        except Exception as e:
            db.session.rollback()
            logging.exception(e)
            return {"message": str(e)}, 400
        

class DirMoveApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    def post(self,category_id:int):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "binding_ids",
            type=list,
            nullable=False,
            location="json",
        )

        args = parser.parse_args()
        binding_ids = args["binding_ids"]
        if not binding_ids:
            raise BadRequest("target_ids is required")
        try:
            newBindings = DictService.move_category_binding(binding_ids=binding_ids,category_id=category_id,account_id=str(current_user.id))
            return {"acmount":len(newBindings),"binding_ids":[newBingding.id for newBingding in newBindings]}, 200
        except Exception as e:
            logging.exception(e)
            return {"message": str(e)}, 400        

class DirUnbindingApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    def delete(self,category_id:int):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "binding_ids",
            type=list,
            nullable=False,
            location="json",
        )

        args = parser.parse_args()
        binding_ids = args["binding_ids"]
        if not binding_ids:
            raise BadRequest("target_ids is required")
        try:
            acmount = 0
            for binding_id in binding_ids:
                acmount += DictService.unbinding_category_object(binding_id=binding_id,category_id=None,target_id=None)
            return {"acmount":len(acmount),"msg":f"unbinding {acmount} success"}, 200
        except Exception as e:
            logging.exception(e)
            return {"msg": str(e)}, 400       
        
api.add_resource(DirBindingApi, "/dir/binding/<string:category_type>/<int:category_id>")
api.add_resource(DirMoveApi, "/dir/<int:category_id>/move")
api.add_resource(DirUnbindingApi, "/dir/<int:category_id>/unbinding")