from flask import request
from controllers.service_api import api
from controllers.service_api.wraps import (
    DatasetApiResource,
    dream_validate_wechat_jwt_token,
)
from flask_restful import marshal, reqparse
from models.account import Account, Tenant
from services.account_service import AccountService, TenantService
from services.app_service import AppService
from services.dc_wechat_app_account_service import WeChatAppAccountService
from fields.app_fields import (
    app_pagination_fields,
)

from controllers.service_api import api
from extensions.ext_database import db
from models.model import Message
from services.file_info_service import FileInfoService


class AddWeChatAppToAccountApi(DatasetApiResource):
    ### 向用户授权Dify机器人权限
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: Account, account_id: str, app_id: str):

        WeChatAppAccountService.add_app_account(tenant_id, account_id, app_id)
        return {"message": "success"}, 200


class GetAppListApi(DatasetApiResource):
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict):
        return WeChatAppAccountService.get_app_list(
            tenant_id, account.get("user_id", None)
        )


class GetAppTokenApi(DatasetApiResource):
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict, app_id: str):
        return WeChatAppAccountService.get_app_token(app_id)


class GetConversationChunkAttachFileApi(DatasetApiResource):

    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict, c_id: str):
        # parser = reqparse.RequestParser()
        # parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        # args = parser.parse_args()
        try:
            account = AccountService.load_user(account.get("user_id", None))
            if not account:
                return {"message": "account not found"}, 401
            # conv = ConversationService.get_conversation(app_model=app_model,conversation_id=c_id,user=account)
            last_message = (
                db.session.query(Message)
                .filter(Message.conversation_id == c_id)
                .order_by(Message.created_at.desc())
                .limit(1)
                .one_or_none()
            )
            if not last_message:
                return {"data": []}, 200
            metadata = last_message.message_metadata_dict
            seg_ids = []
            if "retriever_resources" in metadata:
                for resource in metadata["retriever_resources"]:
                    if (
                        "segment_id" in resource
                        and resource["segment_id"] not in seg_ids
                    ):
                        seg_ids.append(resource["segment_id"])
            result = []
            for seg_id in seg_ids:
                attatches = FileInfoService.get_chunck_attach_files_info(seg_id)
                if "attach" in attatches and len(attatches["attach"]) > 0:
                    result.append({"segment_id": seg_id, "attach": attatches["attach"]})
            return {"data": result}, 200
        except Exception as e:
            raise e


class WeChatAPPUsersApi(DatasetApiResource):

    # 这个方法是注册用户
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict):
        if not account:
            return {"result": "Permission denided"}, 401
        msg, isOwner = TenantService.is_tenant_creater(
            account.get("user_id", None), tenant_id
        )
        if not isOwner:
            return {"result": "Permission denided"}, 401
        tenant = db.session.query(Tenant).filter(Tenant.id == tenant_id).one_or_404()
        allUsers = TenantService.get_tenant_members(tenant=tenant)
        return {
            "count": len(allUsers),
            "users": [
                {
                    "id": user.id,
                    "name": user.name,
                    "is_active": user.is_active,
                    "lasted_active_at": (
                        user.last_login_at.strftime("%Y-%m-%d %H:%M:%S")
                        if user.last_login_at
                        else ""
                    ),
                }
                for user in allUsers
            ],
        }, 200


class WeChatAPPVisibleApi(DatasetApiResource):
    @dream_validate_wechat_jwt_token
    def post(self, tenant_id: str, account: dict):
        wechat_app_id = request.headers.get('wechat_app_id')
        if not account:
            return {"result": "Permission denided"}, 401
        msg, isOwner = TenantService.is_tenant_creater(
            account.get("user_id", None), tenant_id
        )
        if not isOwner:
            return {"result": "Permission denided"}, 401
        argparser = reqparse.RequestParser()
        argparser.add_argument("app_ids", type=list, required=True, location="json")
        # argparser.add_argument('tenant_id', type=str, required=True,location='json')
        argparser.add_argument("visible", type=bool, required=True, location="json")
        args = argparser.parse_args(strict=True)
        app_ids = args["app_ids"]
        visible = args["visible"]
        if WeChatAppAccountService.set_app_visible(tenant_id,app_ids,wechat_app_id,visible,account.get("user_id")):
            return {"message": "success"},200
        return {"message": "fail"}, 400
    
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict):
        wechat_app_id = request.headers.get('wechat_app_id')
        if not account:
            return {"result": "Permission denided"}, 401
        msg, isOwner = TenantService.is_tenant_creater(
            account.get("user_id", None), tenant_id
        )
        if not isOwner:
            return {"result": "Permission denided"}, 401

        return WeChatAppAccountService.get_app_visible_list(tenant_id,wechat_app_id)

class TenantAppListApi(DatasetApiResource):
    @dream_validate_wechat_jwt_token
    def get(self, tenant_id: str, account: dict):
        if not account:
            return {"result": "Permission denided"}, 401
        msg, isOwner = TenantService.is_tenant_creater(
            account.get("user_id", None), tenant_id
        )
        if not isOwner:
            return {"result": "Permission denided"}, 401
        apps = AppService.get_paginate_apps(tenant_id, {"page":1,"limit":100})
        if not apps:
            return {'data': [], 'total': 0, 'page': 1, 'limit': 20, 'has_more': False}

        return marshal(apps, app_pagination_fields)



api.add_resource(
    AddWeChatAppToAccountApi, "/wechat/app/<string:account_id>/add/<string:app_id>"
)
api.add_resource(GetAppListApi, "/wechat/app/list")
api.add_resource(GetAppTokenApi, "/wechat/app/<string:app_id>/token")
api.add_resource(
    GetConversationChunkAttachFileApi, "/wechat/conversation/<string:c_id>/attach"
)
api.add_resource(WeChatAPPUsersApi, "/wechat_app/manage/users")
api.add_resource(WeChatAPPVisibleApi, "/wechat_app/app/visible")
api.add_resource(TenantAppListApi,"/app/all")