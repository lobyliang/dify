from datetime import datetime
import logging
from models.account import Account, AccountIntegrate
from models.dc_wechat_app import WeChatAccountApp, WeChatAgentVisible
from models.model import ApiToken, App
from services.account_service import AccountService
from extensions.ext_database import db
from sqlalchemy import text


class WeChatAppAccountService:

    # 获取当前微信小程序可见Agent列表
    @staticmethod
    def get_app_visible_list(tenant_id: str, wechat_app_id: str) -> list:
        query1 = text(
            """
        select apps.id as app_id,apps.name,apps.description,apps.mode,apps.icon,apps.icon_background,wechat_agent_visible.visible,wechat_agent_visible.created_at,wechat_agent_visible.created_by,wechat_agent_visible.updated_at,wechat_agent_visible.updated_by from wechat_agent_visible left join apps on apps.id=wechat_agent_visible.app_id
        where wechat_agent_visible.tenant_id = :tenant_id and  wechat_agent_visible.wechat_app_id=:wechat_app_id
        """
        )
        allApps = db.session.execute(
            query1, {"tenant_id": tenant_id, "wechat_app_id": wechat_app_id}
        )
        return [
            {
                "app_id": str(row[0]),
                "app_name": row[1],
                "description": row[2],
                "mode": row[3],
                "icon": row[4],
                "icon_background": row[5],
                "visible": row[6],
                "created_at": row[7].strftime("%Y-%m-%d %H:%M:%S") if row[4] else None,
                "created_by": row[8],
                "updated_at": row[9].strftime("%Y-%m-%d %H:%M:%S") if row[6] else None,
                "updated_by": row[10],
            }
            for row in allApps
        ]

    @staticmethod
    def set_app_visible(
        tenant_id: str,
        app_ids: list[str],
        wechat_app_id: str,
        visible: bool,
        account_id: str,
    ):
        try:
            apps = (
                db.session.query(App)
                .filter(App.id.in_(app_ids), App.tenant_id == tenant_id)
                .all()
            )
            for app in apps:
                app_visible = (
                    db.session.query(WeChatAgentVisible)
                    .filter(
                        WeChatAgentVisible.app_id == app.id,
                        WeChatAgentVisible.tenant_id == tenant_id,
                        WeChatAgentVisible.wechat_app_id == wechat_app_id,
                    )
                    .one_or_none()
                )
                if app_visible:
                    app_visible.visible = visible
                    db.session.bulk_update_mappings(
                        WeChatAgentVisible,
                        [
                            {
                                "id": app_visible.id,
                                "visible": visible,
                                "updated_at": datetime.now(),
                                "updated_by": account_id,
                            }
                        ],
                    )

                else:
                    app_visible = WeChatAgentVisible(
                        app_id=app.id,
                        tenant_id=tenant_id,
                        wechat_app_id=wechat_app_id,
                        visible=visible,
                        created_at=datetime.now(),
                        created_by=account_id,
                    )
                    db.session.add(app_visible)
            db.session.commit()
        except Exception as e:
            logging.error(e)
            db.session.rollback()
            return False
        return True

    @staticmethod
    def add_app_account(
        tenant_id: str, account_id: str, app_id: str
    ) -> WeChatAccountApp:
        account = AccountService.load_user(
            account_id
        )  # db.session.query(Account).filter(Account.id == account_id).one_or_none()
        if not account:
            raise Exception("Account not found")

        account_integ = (
            db.session.query(AccountIntegrate)
            .filter(AccountIntegrate.account_id == account_id)
            .one_or_none()
        )
        if not account_integ:
            raise Exception("账号未绑定微信账号")
        openid = account_integ.open_id
        try:
            app_account = WeChatAccountApp(
                account_id=account_id,
                app_id=app_id,
                open_id=openid,
                tenant_id=tenant_id,
            )
            db.session.add(app_account)
            return app_account
        except Exception as e:
            db.session.rollback()
            raise e

    # 个人可用的app列表
    @staticmethod
    def get_app_list(tenant_id: str, account_id: str):
        query1 = text(
            """
        select apps.id,apps.name,apps.description,apps.mode,b.created_at,b.enabled from apps left join (select * from  wechat_account_app where wechat_account_app.account_id=:account_id) as b
        on apps.id=b.id where apps.tenant_id = :tenant_id
        """
        )
        allApps = db.session.execute(
            query1, {"tenant_id": tenant_id, "account_id": account_id}
        )
        return [
            {
                "app_id": str(row[0]),
                "app_name": row[1],
                "description": row[2],
                "mode": row[3],
                "created_at": row[4].strftime("%Y-%m-%d %H:%M:%S") if row[4] else None,
                "enabled": row[5],
            }
            for row in allApps
        ]

    @staticmethod
    def get_app_token(app_id: str):
        # @marshal_with(api_key_list)
        key = (
            db.session.query(ApiToken)
            .filter(ApiToken.type == "app", ApiToken.app_id == app_id)
            .one_or_none()
        )
        return key.token if key else None
