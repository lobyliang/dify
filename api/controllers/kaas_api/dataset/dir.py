from email.policy import default
from flask_login import current_user
from flask_restful import Resource, marshal, marshal_with, reqparse
from controllers.console.setup import setup_required
from libs.login import kaas_login_required
from fields.dataset_fields import dataset_detail_fields
from controllers.kaas_api import api
from services.dataset_service import DatasetService
from services.dc_dict_service import DictService
from werkzeug.exceptions import BadRequest
from flask_restful import Resource, fields, marshal_with
from werkzeug.exceptions import NotFound
dir_fields = {
    "id": fields.String,
    "parent_id": fields.Integer,
    "name": fields.String,
    "key": fields.String,
    "type": fields.String,
}
category_view_fields = {
    "id": fields.Integer,
    "name": fields.String,
    "key": fields.String,
}
bindings_fields = {
    "binding_id":fields.String,
    "target_id":fields.String,
}
categoris_dirs_view_fields = {
    "dirs":fields.Nested(category_view_fields),
}
categoris_view_fields = {
    "dirs":fields.List(fields.Nested(category_view_fields)),
    "targets":fields.List(fields.Nested(bindings_fields)),
}
class CreateDirApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    @marshal_with(dir_fields)
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "parent_id",
            type=int,
            nullable=True,
            location="json",
        )
        parser.add_argument(
            "name",
            type=str,
            nullable=False,
            location="json",
        )
        parser.add_argument(
            "key",
            type=str,
            nullable=True,
            default=None,
            location="json",
        )
        parser.add_argument(
            "type",
            type=str,
            nullable=False,
            location="json",
        )
        args = parser.parse_args()

        try:
            category = DictService.add_category(
                tenant_id=str(current_user.current_tenant_id),
                name=args["name"],
                key=args["key"],
                type=args["type"],
                parent_id=args["parent_id"],
                account_id=current_user.id,
            )
            return category, 200
        except Exception as e:
            raise e

class DirRenameApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    @marshal_with(dir_fields)
    def put(self,category_id:int, new_name:str):
        category = DictService.get_category_by_id(category_id)
        if not category:
            raise NotFound("category not found")
        return DictService.update_category(category_id, new_name, category.key)
    

class DataSetDirRootViewApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    def get(self,):
        category_type = "DataSet"
        category = DictService.get_category_root(str(current_user.current_tenant_id), category_type)
        if not category:
            raise NotFound("type of category not found")
        childs = DictService.get_category_childs(category.id)
        tragets = DictService.get_category_bindings(category.id)

        if category_type == "DataSet":
            datasets = []
            for traget in tragets:
                ds = DatasetService.get_dataset(traget.target_id)
                if ds.permission == "only_me" and current_user.id != ds.created_by:
                    continue
                ds_dict = marshal(ds,dataset_detail_fields)
                ds_dict["binding_id"] = traget.id
                datasets.append(ds_dict)
            result = {"dirs":[{"id":child.id,"name":child.name,"key":child.key} for child in childs]}
            
            others = DictService.get_root_datasets(str(current_user.current_tenant_id),str(current_user.id))
            for other in others:
                ds_dict = marshal(other,dataset_detail_fields)
                ds_dict["binding_id"] = None
                datasets.append(ds_dict)
            result["datasets"] = datasets
            return result,200
        
class DirRootViewApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    def get(self,category_type:str):
        category = DictService.get_category_root(str(current_user.current_tenant_id), category_type)
        if not category:
            raise NotFound("type of category not found")
        childs = DictService.get_category_childs(category.id)
        tragets = DictService.get_category_bindings(category.id)

        return marshal({"dirs":childs,"targets": tragets},categoris_view_fields),200

class DataSetDirViewApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    def get(self,category_id:int):
        # category_type = "DataSet"
        category = DictService.get_category_by_id(category_id)
        if not category:
            raise NotFound("type of category not found")
        childs = DictService.get_category_childs(category.id)
        tragets = DictService.get_category_bindings(category.id)
    
        datasets = []
        for traget in tragets:
            ds = DatasetService.get_dataset(traget.target_id)
            if ds.permission == "only_me" and current_user.id != ds.created_by:
                continue
            ds_dict = marshal(ds,dataset_detail_fields)
            ds_dict["binding_id"] = traget.id
            datasets.append(ds_dict)
        result = {"dirs":[{"id":child.id,"name":child.name,"key":child.key} for child in childs]}
        result["datasets"] = datasets
        return result,200


class DirViewApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    def get(self,category_type:str,category_id:int):
        category = DictService.get_category_by_id(category_id)
        if not category:
            raise NotFound("type of category not found")
        if category.type != category_type:
            raise NotFound("type of category not found")
        childs = DictService.get_category_childs(category.id)
        tragets = DictService.get_category_bindings(category.id)
        return marshal({"dirs":childs,"targets":tragets},categoris_view_fields),200
                
class DirTreeApi(Resource):

    # @validate_dataset_token()
    # @setup_required
    # @kaas_login_required
    def get(self,category_type:str,parent_id:int):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "targets",
            type=bool,
            nullable=True,
            default=False,
            location="args",
        )
        args = parser.parse_args()
        get_targets = args["targets"]
        if parent_id !=0:
            category = DictService.get_category_by_id(parent_id)
        else:
            category = DictService.get_category_root(str(current_user.current_tenant_id), category_type)
        if not category:
            raise NotFound("type of category not found")
        if category.type != category_type:
            raise BadRequest("type of category not match")
        if parent_id ==0:
            parent_id = category.id
        tenant_id = str(current_user.current_tenant_id)
        account_id = str(current_user.id)
        return DictService.get_category_tree(category_type,parent_id,tenant_id,account_id,get_targets)
        
api.add_resource(CreateDirApi, "/dir")
api.add_resource(DirRenameApi, "/dir/rename/<int:category_id>/<string:new_name>")
api.add_resource(DataSetDirRootViewApi, "/dir/view/root/dataset")
api.add_resource(DirRootViewApi, "/dir/view/root/<string:category_type>")
api.add_resource(DataSetDirViewApi, "/dir/view/dataset/<int:category_id>")
api.add_resource(DirViewApi, "/dir/view/<string:category_type>/<int:category_id>")
api.add_resource(DirTreeApi, "/dir/tree/<string:category_type>/<int:parent_id>")
