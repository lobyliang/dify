from extensions.ext_database import db
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import UUID

from models import StringUUID

class WeChatAccountApp(db.Model):
    __tablename__ = "wechat_account_app"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="account_app_pkey"),
        db.Index("account_app_accountid_idx", "account_id"),
    )
    id = db.Column(UUID, server_default=db.text("uuid_generate_v4()"))
    tenant_id = db.Column(UUID, nullable=False)
    account_id = db.Column(UUID, nullable=False)
    app_id = db.Column(UUID, nullable=False)
    open_id = db.Column(db.String(128), nullable=True)
    # phone = db.Column(db.String(64), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    enabled = db.Column(db.Boolean, nullable=False, server_default=db.text("true"))



    def to_dict(self):
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "account_id": str(self.account_id),
            "app_id": str(self.app_id),
            "openid": self.openid,
            "phone": self.phone,
            "created_at": self.created_at,
            "enabled": self.enabled,

        }
    
class WeChatTenantSecretInfo(db.Model):
    __tablename__ = "wechat_tenant_secret_info"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="wechat_tenant_secret_info_pkey"),
        db.Index("wechat_tenant_secret_info_idx", "tenant_id"),
    )
    id = db.Column(UUID, server_default=db.text("uuid_generate_v4()"))
    tenant_id = db.Column(UUID, nullable=False)
    wechat_app_id = db.Column(db.String(255), nullable=False)
    wechat_app_secret = db.Column(db.String(255), nullable=False)
    app_type=db.Column(db.String(32), nullable=False,server_default='app')
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP(0)")
    )
    created_by = db.Column(db.String(255), nullable=True, server_default='admin')
    enabled = db.Column(db.Boolean, nullable=False, server_default=db.text("true"))
    

