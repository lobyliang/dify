import copy
import logging
from flask import current_app,  request
from flask_restful import Resource, reqparse
import sqlalchemy
import sqlalchemy.exc
from werkzeug.exceptions import Conflict
from controllers.kaas_api.wraps import DreamAIResource
from controllers.kaas_api import api
from services.account_service import AccountService, TenantService
from extensions.ext_database import db
import sqlalchemy
class DRReisterApi(DreamAIResource):
    def post(self,ext_user_id:str,ext_tenant_id:str,ext_phone_no:str):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('phone', type=str, required=False, default=None, location='json')
            parser.add_argument('tenant_no', type=str, required=False, default=None, location='json')
            args = parser.parse_args()
            if args['tenant_no']:
                ext_tenant_id = args['tenant_no']
                ext_phone_no = args['phone']
            tenant = TenantService.get_tenant_by_ext_tenant_id(ext_tenant_id=ext_tenant_id)
            email = (
                    f"""{ext_phone_no}"""
                    + "@"
                    + current_app.config["DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN"]
                )
            account = AccountService.load_by_email(email=email)
            if not account:
                account = AccountService.create_account(email=email,
                            name=f"{ext_phone_no}_{ext_user_id}",
                            interface_language="zh-Hans",
                            password='123456',
                            timezone='Asia/Shanghai')
            TenantService.create_tenant_member(tenant=tenant,account=account)
        except sqlalchemy.exc.IntegrityError as e:
            raise Conflict(f"账户{ext_phone_no},id:{ext_user_id}已注册")
        except Exception as e:
            logging.error(f"create account error:{e}")
            db.session.rollback()
            raise Conflict(f"账户{ext_phone_no},id:{ext_user_id}已注册")
        return {'user_id':str(account.id),'tenant_id':str(tenant.id),'msg':'注册成功'},200

class DRUnregisterApi(DreamAIResource):
    def post(self,ext_user_id:str,ext_tenant_id:str,ext_phone_no:str):
        try:
            tenant = TenantService.get_tenant_by_ext_tenant_id(ext_tenant_id=ext_tenant_id)
            email = (
                    f"""{ext_phone_no}"""
                    + "@"
                    + current_app.config["DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN"]
                )
            account = AccountService.load_by_email(email=email)
            if not account:
                raise Conflict(f"账户{ext_phone_no},id:{ext_user_id}未注册")
            TenantService.remove_member_from_tenant(tenant=tenant,account=account)
        except Exception as e:
            logging.error(f"unregister account error:{e}")
            db.session.rollback()
            raise Conflict(f"账户{ext_phone_no},id:{ext_user_id} 注销失败")
        except Conflict as e:
            raise e
        return {'user_id':str(account.id),'tenant_id':str(tenant.id),'msg':'注销成功'},200

class DRLoginApi(DreamAIResource):
    def post(self,ext_user_id:str,ext_tenant_id:str,ext_phone_no:str):
        parser = reqparse.RequestParser()
        parser.add_argument('remember_me', type=bool, required=False, default=False, location='args')
        args = parser.parse_args()
        email = (
                f"""{ext_phone_no}"""
                + "@"
                + current_app.config["DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN"]
            )
        # todo: Verify the recaptcha
        try:
            account = AccountService.load_by_email(email)
            if not account:
                return {'code': 'unauthorized', 'message': 'account not found'}, 403

            # SELF_HOSTED only have one workspace
            # tenants = TenantService.get_join_tenants(account)
            tenant = TenantService.get_tenant_by_ext_tenant_id(ext_tenant_id)
            if not tenant:
                return {'result': 'fail', 'data': 'workspace not found, please contact system admin to invite you to join in a workspace'}, 401

            TenantService.switch_tenant(account, tenant.id)
            
            AccountService.update_last_login(account, request)

            # todo: return the user info
            token = AccountService.get_account_jwt_token(account)
        except Exception as e:
            return {'result': 'fail', 'data': str(e)}, 401

        return {'result': 'success', 'data': token},200
    
class DRFuncsApi(Resource):
    funcs = {
        "app_name":"梦软知识库系统",
        "un_key":"001001",
        "version":"1.0",
        "funcs":[
            {
                "menuId":1,
                "menuName":"管理公共知识库",
                "defaultRoles":"admin",
                "parentId":0,
                "orderNum":1,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"M",
                "perms":"kaas:public",
                "remark":None
            },
            {
                "menuId":2,
                "menuName":"创建公共知识库",
                "defaultRoles":"admin",
                "parentId":1,
                "orderNum":1,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"C",
                "perms":"kaas:create_public",
                "remark":None
            },
            {
                "menuId":3,
                "menuName":"删除公共知识库",
                "defaultRoles":"admin",
                "parentId":1,
                "orderNum":2,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"C",
                "perms":"kaas:del_public",
                "remark":None
            },
            {
                "menuId":4,
                "menuName":"管理私有知识库",
                "defaultRoles":"admin",
                "parentId":0,
                "orderNum":2,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"C",
                "perms":"kaas:private",
                "remark":None
            },
            {
                "menuId":5,
                "menuName":"管理知识库机器人",
                "defaultRoles":"admin",
                "parentId":0,
                "orderNum":3,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"C",
                "perms":"kaas:agent",
                "remark":"添加删除机器人"
            },
            {
                "menuId":6,
                "menuName":"访问知识库机器人",
                "defaultRoles":"admin,common",
                "parentId":0,
                "orderNum":4,
                "path":None,
                "component":None,
                "queryParam":None,
                "menuType":"C",
                "perms":"kaas:agent:qa",
                "remark":"知识库机器人问答"
            }
        ]
    }
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument('base_id', type=int, required=True,  location='args')
        args = parser.parse_args()
        base_id = args['base_id']
        funcs = copy.deepcopy(DRFuncsApi.funcs)
        for func in funcs['funcs']:
            func['menuId'] += base_id
            func['parentId'] += base_id
        return funcs,200
api.add_resource(DRReisterApi, "/auth/register")

api.add_resource(DRLoginApi, "/auth/login")
api.add_resource(DRFuncsApi, "/auth/funcs")
api.add_resource(DRUnregisterApi, "/auth/unregister")