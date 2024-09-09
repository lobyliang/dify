
from functools import wraps
from flask import current_app, request
from flask_restful import Resource
from werkzeug.exceptions import Forbidden, Unauthorized
from libs.passport import PassportService
from services.account_service import AccountService, TenantService
from services.dc_dream_ai_service import DreamAIService



def validate_and_get_dream_ai_token():
    auth_header = request.headers.get('Authorization')
    if auth_header is None or ' ' not in auth_header:
            raise Unauthorized("Authorization header must be provided and start with 'Bearer'")
    auth_scheme, auth_token = auth_header.split(None, 1)
    auth_scheme = auth_scheme.lower()

    if auth_scheme != 'bearer':
        raise Unauthorized("Authorization scheme must be 'Bearer'")
    
    passportService = PassportService()
    passportService.sk = current_app.config["DREAM_CLOUD_SECRET_KEY"]
    
    try:
        token = passportService.verify(auth_token)
        ext_tenant_id = token["tenantId"]
        if TenantService.get_extent_tenant_count(ext_tenant_id=ext_tenant_id)==0:
            raise Forbidden("请先创建租户")    
    except Exception as e:
        raise Forbidden(f"您无权访问,{str(e)}")
    return token["userId"],token["tenantId"],token["phonenumber"]
    
def validate_and_get_kaas_token():
    # account = AccountService.load_by_email('lobyliang@qq.com')
    # AccountService.get_account_jwt_token(account)
    auth_header = request.headers.get('KaasToken')
    if auth_header is None or ' ' not in auth_header:
            raise Unauthorized("Authorization header must be provided and start with 'Bearer'")
    auth_scheme, auth_token = auth_header.split(None, 1)
    auth_scheme = auth_scheme.lower()

    if auth_scheme != 'bearer':
        raise Unauthorized("Authorization scheme must be 'Bearer'")
    
    passportService = PassportService()
    
    try:
        token = passportService.verify(auth_token) 
    except Exception as e:
        raise Forbidden(f"您无权访问,{str(e)}")
    
    return token["user_id"]
def validate_dream_ai_token(funcs=None,getExtUserId=False,getExtTenantId=False,getExtPhoneNo=False):
    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            ext_user_id,ext_tenant_id,ext_phone_no = validate_and_get_dream_ai_token()
            if getExtUserId:
                kwargs['ext_user_id'] = ext_user_id
            if getExtTenantId:
                kwargs['ext_tenant_id'] = ext_tenant_id
            if getExtPhoneNo:
                kwargs['ext_phone_no'] = ext_phone_no
            if funcs:
                if not DreamAIService.check_permission(funcs):
                    raise Forbidden("您无权访问")
            return view(*args, **kwargs)
        return decorated

    # if funcs:
    return decorator

    # if view is None, it means that the decorator is used without parentheses
    # use the decorator as a function for method_decorators
    # return decorator
def validate_kaas_token(view=None):
    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            validate_and_get_kaas_token()
            return view(*args, **kwargs)
        return decorated

    if view:
        return decorator(view)
    return decorator

# 检查KaaS Token 是否登录
class KaaSResource(Resource):
    method_decorators = [validate_kaas_token()]

# 检查 Dream AI Token 是否登录
class DreamAIResource(Resource):
    method_decorators = [validate_dream_ai_token(getExtUserId=True,getExtTenantId=True,getExtPhoneNo=True)]

# 检查 Dream AI 账号是否有 管理公共知识库权限
class PublicKaaSDreamAIResource(Resource):
    method_decorators = [validate_dream_ai_token(funcs={'and':['kaas:public']})]    