

from enum import Enum
from extensions.ext_database import db
from models.dc_wechat_app import WeChatTenantSecretInfo

class WeChatAppType(Enum):
    """
    应用类型
    """
    WECHAT_MINI_APP = "app"
    WECHAT_WEB_APP = "web"
    WECHAT_OPEN_APP = "open"

class WechatTenantInfoService:

    """
    微信租户信息服务
    """
    @staticmethod
    def add_wechat_tenant_info(tenant_id:str,wechat_app_id:str,wechat_app_secret:str,app_type:WeChatAppType,creater:str):
        if not wechat_app_id or not wechat_app_secret:
            raise Exception("wechat_app_id or wechat_app_secret is empty")
        info = WeChatTenantSecretInfo(tenant_id=tenant_id,wechat_app_id=wechat_app_id,wechat_app_secret=wechat_app_secret,app_type=app_type.value,created_by=creater)
        db.session.add(info)
        db.session.commit()

    @staticmethod
    def get_wechat_tenant_info(tenant_id:str,wechat_app_id:str,app_type:WeChatAppType):
        """
        获取微信租户信息
        :param tenant_id:
        :return:
        """
        info =  db.session.query(WeChatTenantSecretInfo).filter(WeChatTenantSecretInfo.tenant_id == tenant_id,
                                                 WeChatTenantSecretInfo.app_type == app_type.value,
                                                 WeChatTenantSecretInfo.wechat_app_id == wechat_app_id).one_or_none()
        if info:
            return {"app_id":info.wechat_app_id,"app_secret":info.wechat_app_secret}
        else:
            return None        