from datetime import datetime, timezone
from typing import Optional
from flask import current_app, request
from controllers.service_api.wraps import DatasetApiResource
from models.account import Account, AccountStatus, Tenant
from controllers.service_api import api
from services.account_service import AccountService, TenantService
from extensions.ext_database import db
from libs.dc_wechat_oauth import WeChatAppOAuth


def _get_account_by_openid_or_email(provider: str, open_id: str,email:str=None) -> Optional[Account]:
    account = Account.get_by_openid(provider, open_id)

    if not account:
        account = Account.query.filter_by(email=email).first()

    return account

class WeChatAPPLoginApi(DatasetApiResource):
    _provider = 'wechat_app'

    # 登录
    def get(self,tenant_id:str,code:str):
        
        tokenDict = WeChatAppOAuth.get_access_token(code)
        openid = tokenDict['openid']

        account = _get_account_by_openid_or_email(self._provider,openid)
        if account:
            if account.status == AccountStatus.BANNED.value or account.status == AccountStatus.CLOSED.value:
                return {'error': 'Account is banned or closed.'}, 403
            if account.status == AccountStatus.PENDING.value:
                account.status = AccountStatus.ACTIVE.value
                account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()     

            AccountService.update_last_login(account, request)
            token = AccountService.get_account_jwt_token(account)
            owner = TenantService.get_tenant_creater(tenant_id)
            isOwner = False
            if owner.name.strip() == account.name.strip():
                isOwner = True
            return {'result': 'success', 'data': token,'isOwner':isOwner},200
        # tokenDict['account_id'] = account_id

        # else:
        #     account = RegisterService.register(user_info.email, user_info.name, open_id=openid, provider=self._provider)
        #     account_id = account.id
        #     tokenDict['account_id'] = account_id
        return {'result': 'failed'},403
        
class WeChatAPPRegisterApi(DatasetApiResource):
    _provider = 'wechat_app'
    # 这个方法是注册用户
    def get(self,tenant_id:str,code:str,phoneCode:str,):
        tokenDict = WeChatAppOAuth.get_access_token(code)
        openid = tokenDict['openid']
        phonDict = WeChatAppOAuth.get_phon_no(phoneCode,openid)
        purePhoneNumber = phonDict['purePhoneNumber']
        account = _get_account_by_openid_or_email(self._provider,openid)
        if account:
            return {'msg':'该手机号已注册，请直接登录'},400
        else:
            email = f"{purePhoneNumber}@{current_app.config['DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN']}"
            account = _get_account_by_openid_or_email(provider=self._provider,open_id=None,email=email)
            if not account:
            # account = RegisterService.register(email, purePhoneNumber, open_id=purePhoneNumber, provider=self._provider)
                account = AccountService.create_account(email,purePhoneNumber,interface_language='zh-CN',interface_theme='light',timezone='Asia/Shanghai')#
            AccountService.link_account_integrate(self._provider, openid, account)
            if not TenantService.is_tenant_creater(account.id,tenant_id):
                tenant = db.session.query(Tenant).filter(Tenant.id == tenant_id).one_or_404()
                TenantService.create_tenant_member(tenant=tenant,account= account)

        if not account:
            return {'result': 'failed'},401
        if account.status == AccountStatus.BANNED.value or account.status == AccountStatus.CLOSED.value:
            return {'error': 'Account is banned or closed.'}, 403
        if account.status == AccountStatus.PENDING.value:
            account.status = AccountStatus.ACTIVE.value
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()        

        AccountService.update_last_login(account, request)
        token = AccountService.get_account_jwt_token(account)
        owner = TenantService.get_tenant_creater(tenant_id)
        isOwner = False
        if owner.name.strip() == account.name.strip():
            isOwner = True
        return {'result': 'success', 'data': token,'isOwner':isOwner},200


api.add_resource(WeChatAPPLoginApi, '/wechat_app/login/<string:code>')
api.add_resource(WeChatAPPRegisterApi, '/wechat_app/register/<string:code>/<string:phoneCode>')


