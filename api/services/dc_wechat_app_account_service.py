
from models.account import Account, AccountIntegrate
from models.dc_wechat_app import WeChatAccountApp
from models.model import ApiToken, App
from services.account_service import AccountService
from extensions.ext_database import db
from sqlalchemy import  text
class WeChatAppAccountService:
    @staticmethod
    def add_app_account(tenant_id:str,account_id: str, app_id: str) -> WeChatAccountApp:
        account = AccountService.load_user(account_id) #db.session.query(Account).filter(Account.id == account_id).one_or_none()
        if not account:
            raise Exception('Account not found')
        
        account_integ = db.session.query(AccountIntegrate).filter(AccountIntegrate.account_id == account_id).one_or_none()
        if not account_integ:
            raise Exception('账号未绑定微信账号')
        openid = account_integ.open_id
        try:
            app_account = WeChatAccountApp(
                account_id=account_id,
                app_id=app_id,
                open_id=openid,
                tenant_id=tenant_id
            )
            db.session.add(app_account)
            return app_account
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_app_list(tenant_id: str, account_id: str):
        query1=text("""
        select apps.id,apps.name,apps.description,apps.mode,b.created_at,b.enabled from apps left join (select * from  wechat_account_app where wechat_account_app.account_id=:account_id) as b
        on apps.id=b.id where apps.tenant_id = :tenant_id
        """)
        allApps = db.session.execute(query1,{'tenant_id':tenant_id,'account_id':account_id})
        return [{"app_id":str(row[0]),
                "app_name":row[1],
                "description":row[2],
                "mode":row[3],
                "created_at":row[4].strftime("%Y-%m-%d %H:%M:%S") if row[4] else None,
                "enabled":row[5]} for row in allApps]
    
    @staticmethod
    def get_app_token(app_id:str):
        # @marshal_with(api_key_list)
        key = db.session.query(ApiToken). \
            filter(ApiToken.type == 'app',ApiToken.app_id == app_id). \
            one_or_none()
        return key.token if key else None