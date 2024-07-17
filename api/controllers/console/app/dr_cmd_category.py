import logging
from flask_restful import Resource, marshal_with,marshal_with,fields
from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required

from libs.login import login_required
from services.chat_robot_service import ChatRebotService
from werkzeug.exceptions import InternalServerError   
class CmdCategoriesList(Resource):
    # @validate_cmd_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=False))
    app_categories_fields = {
        'id': fields.String,
        'category': fields.String,
        'name':fields.String,
        'is_del':fields.Boolean,
        'created_at':fields.DateTime,
        # 'data': fields.List(fields.Nested(message_fields))
    }
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_categories_fields)
    def get(self):
        
        try:
            categories = ChatRebotService.get_app_categories()

            return  categories #Response(response=json.dumps(categories), status=200, mimetype='application/json')
    
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()

api.add_resource(CmdCategoriesList, '/chat_robot/categories/list')