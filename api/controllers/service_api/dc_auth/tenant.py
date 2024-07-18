from datetime import datetime, timezone
import json
import logging
from flask import current_app
from flask_restful import Resource, reqparse
from controllers.service_api.wraps import DatasetApiResource
from core.model_runtime.entities.model_entities import ProviderModel
from core.model_runtime.utils.encoders import jsonable_encoder
from libs.passport import PassportService
from models.account import Account, AccountStatus
from models.model import ApiToken
from models.provider import TenantDefaultModel
from controllers.service_api import api
from services.account_service import RegisterService, TenantService
from services.model_provider_service import ModelProviderService
from .default_model_service import DefaultModelService
from extensions.ext_database import db

# 以下是各模型的 credentials 取值
#     Volcengine={ #火山引擎，添加模型
#   "volc_region": "cn-beijing",
#   "api_endpoint_host": "maas-api.ml-platform-cn-beijing.volces.com",
#   "volc_access_key_id": "123",
#   "volc_secret_access_key": "123",
#   "endpoint_id": "123123",
#   "base_model_name": "Doubao-pro-4k"
# }
#     yi={# 零一万物 添加供应商
#   "api_key": "1231",
#   "endpoint_url": "123"
# }
#     chatglm={# chatglm,本地，地址 添加供应商
#   "api_base": "12312"
# }
#     jina2={ #jina 添加模型
#   "base_url": "https://api.jina.ai/v1",
#   "context_size": "8192",
#   "api_key": "123"
# }
#     jina={ #jina 先添加供应商，再添加模型
#   "api_key": "123123"
# }
#     wenxin={ # 文心一言 添加供应商
#   "api_key": "123",
#   "secret_key": "123"
# }
#     togetherai={ # togetherai，添加模型，
#   "mode": "chat",
#   "context_size": "4096",
#   "max_tokens_to_sample": "4096",
#   "api_key": "123"
# }
#     nvidia = { 添加供应商
#   "api_key": "123123"
# }
#     tongyi={ # 通义千问 添加供应商
#   "dashscope_api_key": "[__HIDDEN__]"
# }
#     spark = { 讯飞星火  添加供应商
#   "app_id": "456",
#   "api_secret": "345",
#   "api_key": "345"
# }
#     zhipuai={ #智普AI 添加供应商
#   "api_key": "555"
# }
#     spart= { #讯飞星火 添加供应商
#   "app_id": "456",
#   "api_secret": "345",
#   "api_key": "345"
# }


# 还要配置默认模型
class TenantManage(Resource):
    _initialized = False
    llm_config = None
    embeddings_config = None
    reranking_config = None
    providers = []
    data_set_token_prefix = "dataset-"
    data_set_resource_type = "dataset"
    app_token_prefix = "app-"
    app_resource_type = "app"
    # 所有需要先添加供应商的模型厂家
    providers_with_key = [
        "wenxin",
        "openai",
        "jina",
        "chatglm",
        "yi",
        "zhipuai",
        "spart",
        "spark",
        "tongyi",
        "nvidia",
    ]

    @staticmethod
    def setDefaultModle(tenant_id: str):
        if not TenantManage._initialized:
            logging.info("开始初始化默认模型")
            all_providers = []
            TenantManage.llm_config = {}
            TenantManage.llm_config["model"] = current_app.config["DEFAULT_LLM_MODEL"]
            TenantManage.llm_config["model_type"] = "llm"
            TenantManage.llm_config["provider"] = current_app.config[
                "DEFAULT_LLM_MODEL_PROVIDER"
            ]
            TenantManage.llm_config["config_from"] = (
                "predefined-model"
                if TenantManage.llm_config["provider"]
                in TenantManage.providers_with_key
                else None
            )
            # TenantManage.llm_config["credentials"]={}
            # TenantManage.llm_config["credentials"]["server_url"] =current_app.config["DEFAULT_LLM_MODEL_SERVER_URL"]
            # TenantManage.llm_config["credentials"]["model_uid"] = current_app.config["DEFAULT_LLM_MODEL_MODEL_UID"]
            # TenantManage.llm_config["credentials"]["dashscope_api_key"] = current_app.config["DEFAULT_LLM_MODEL_API_KEY"]
            TenantManage.llm_config["credentials"] = json.loads(
                current_app.config["DEFAULT_LLM_MODEL_CREDENTIALS"]
            )
            TenantManage.llm_config["load_balancing"] = {}
            TenantManage.llm_config["load_balancing"]["enabled"] = False
            TenantManage.llm_config["load_balancing"]["configs"] = []
            if (
                current_app.config["DEFAULT_LLM_MODEL_PROVIDER"]
                in TenantManage.providers_with_key
            ):
                TenantManage.providers.append(
                    {
                        "provider": current_app.config["DEFAULT_LLM_MODEL_PROVIDER"],
                        "credentials": json.loads(
                            current_app.config["DEFAULT_LLM_MODEL_CREDENTIALS"]
                        ),
                    }
                )
                all_providers.append(current_app.config["DEFAULT_LLM_MODEL_PROVIDER"])

            TenantManage.embeddings_config = {}
            TenantManage.embeddings_config["model"] = current_app.config[
                "DEFAULT_EMBEDDING_MODEL"
            ]
            TenantManage.embeddings_config["model_type"] = "text-embedding"
            TenantManage.embeddings_config["provider"] = current_app.config[
                "DEFAULT_EMBEDDING_MODEL_PROVIDER"
            ]
            TenantManage.embeddings_config["config_from"] = (
                "predefined-model"
                if TenantManage.embeddings_config["provider"]
                in TenantManage.providers_with_key
                else None
            )
            # TenantManage.embeddings_config["credentials"]={}
            # TenantManage.embeddings_config["credentials"]["server_url"] =current_app.config["DEFAULT_EMBEDDING_MODEL_SERVER_URL"]
            # TenantManage.embeddings_config["credentials"]["model_uid"] = current_app.config["DEFAULT_EMBEDDING_MODEL_MODEL_UID"]
            TenantManage.embeddings_config["credentials"] = json.loads(
                current_app.config["DEFAULT_EMBEDDING_MODEL_CREDENTIALS"]
            )
            TenantManage.embeddings_config["load_balancing"] = {}
            TenantManage.embeddings_config["load_balancing"]["enabled"] = False
            TenantManage.embeddings_config["load_balancing"]["configs"] = []
            if (
                current_app.config["DEFAULT_LLM_MODEL_PROVIDER"]
                in TenantManage.providers_with_key
                and current_app.config["DEFAULT_LLM_MODEL_PROVIDER"]
                not in all_providers
            ):
                TenantManage.providers.append(
                    {
                        "provider": current_app.config["DEFAULT_LLM_MODEL_PROVIDER"],
                        "credentials": json.loads(
                            current_app.config["DEFAULT_LLM_MODEL_CREDENTIALS"]
                        ),
                    }
                )
                all_providers.append(current_app.config["DEFAULT_LLM_MODEL_PROVIDER"])

            TenantManage.reranking_config = {}
            TenantManage.reranking_config["model"] = current_app.config[
                "DEFAULT_RERANKING_MODEL"
            ]
            TenantManage.reranking_config["model_type"] = "rerank"
            TenantManage.reranking_config["provider"] = current_app.config[
                "DEFAULT_RERANKING_MODEL_PROVIDER"
            ]
            TenantManage.reranking_config["config_from"] = (
                "predefined-model"
                if TenantManage.reranking_config["provider"]
                in TenantManage.providers_with_key
                else None
            )
            # TenantManage.reranking_config["credentials"]={}
            # TenantManage.reranking_config["credentials"]["server_url"] =current_app.config["DEFAULT_RERANKING_MODEL_SERVER_URL"]
            # TenantManage.reranking_config["credentials"]["model_uid"] = current_app.config["DEFAULT_RERANKING_MODEL_MODEL_UID"]
            TenantManage.reranking_config["credentials"] = json.loads(
                current_app.config["DEFAULT_RERANKING_MODEL_CREDENTIALS"]
            )
            TenantManage.reranking_config["load_balancing"] = {}
            TenantManage.reranking_config["load_balancing"]["enabled"] = False
            TenantManage.reranking_config["load_balancing"]["configs"] = []
            TenantManage._initialized = True
            if (
                current_app.config["DEFAULT_LLM_MODEL_PROVIDER"]
                in TenantManage.providers_with_key
                and current_app.config["DEFAULT_LLM_MODEL_PROVIDER"]
                not in all_providers
            ):
                TenantManage.providers.append(
                    {
                        "provider": current_app.config["DEFAULT_LLM_MODEL_PROVIDER"],
                        "credentials": json.loads(
                            current_app.config["DEFAULT_LLM_MODEL_CREDENTIALS"]
                        ),
                    }
                )
                all_providers.append(current_app.config["DEFAULT_LLM_MODEL_PROVIDER"])
            logging.info("默认模型初始化完成")

        for provider_config in TenantManage.providers:
            logging.info("开始初始化默认供应商{provider_config}")
            DefaultModelService.add_model(tenant_id, provider_config)

        DefaultModelService.add_model(tenant_id, TenantManage.llm_config)
        DefaultModelService.setDefaultModel(tenant_id, TenantManage.llm_config)

        DefaultModelService.add_model(tenant_id, TenantManage.reranking_config)
        DefaultModelService.setDefaultModel(tenant_id, TenantManage.reranking_config)

        DefaultModelService.add_model(tenant_id, TenantManage.embeddings_config)
        DefaultModelService.setDefaultModel(tenant_id, TenantManage.embeddings_config)

    # @validate_dataset_token()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "email", type=str, required=False, nullable=True, location="json"
        )
        parser.add_argument(
            "user_name", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument(
            "password", type=str, required=False, nullable=True, location="json"
        )
        parser.add_argument(
            "token", type=str, required=False, nullable=True, location="json"
        )
        args = parser.parse_args()
        email = args["email"]
        try:
            # {'loginType': 'login',
            # 'loginId': 'app_user:1795021603947073538',
            # 'rnStr': '2aqbF7ZRQ18qpbiFlUUaUSMU5rH99RU6',
            # 'clientid': 'e5cd7e4891bf95d1d19206ce24a7b32e',
            # 'tenantId': '000000',
            # 'userId': 1795021603947073538,
            # 'deptId': 100,
            # 'baseUserId': 1795021603947073538}
            passportService = PassportService()
            passportService.sk = current_app.config["DREAM_CLOUD_SECRET_KEY"]
            token = passportService.verify(args["token"])
            ext_user_id = token["userId"]
            ext_tenant_id = token["tenantId"]
        except Exception as e:
            return {"message": f"Unauthorized:{e}"}, 400

        if not args["user_name"]:
            return "user name must be set", 400
        if not email:
            email = (
                args["user_name"]
                + "@"
                + current_app.config["DEFAULT_DERAM_CLOUD_EMAIL_DOMAIN"]
            )

        try:
            old_account = (
                db.session.query(Account).filter(Account.email == args["email"]).first()
            )
            if old_account:
                return f"Account {email} aready exits", 400
            password = "qwer1234"
            if args["password"]:
                password = args["password"]
            account = RegisterService.register(
                email=email,
                name=args["user_name"],
                password=password,
                open_id=None,
                provider=None,
            )

            account.interface_language = "chinese"
            account.status = AccountStatus.ACTIVE.value
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            TenantService.create_owner_tenant_if_not_exist(account)
            tenants = TenantService.get_join_tenants(account)
            tenant = tenants[0]

            custom_config = {"user_name": args["user_name"]}
            if args["token"]:
                custom_config["extent_tenant_id"] = ext_tenant_id
                custom_config["extent_user_id"] = ext_user_id
            tenant.custom_config = json.dumps(custom_config)
            db.session.commit()

            TenantManage.setDefaultModle(str(tenant.id))

            dataset_api_key = TenantManage.create_dataset_api_key(tenant.id)
            logging.info(f"{args['user_name']} create tenant {tenant.id} success")

        except Exception as e:
            # TODO 删除创建的模型，账户，租户，和默认模型
            logging.error(
                f"{args['user_name']} create tenant {tenant.id} failed for {e}"
            )
            TenantManage.clear_tenant(tenant.id)
            return {"msg": "Failed to create tenant", "error": str(e)}, 500

        return {
            "tannt_id": tenant.id,
            "account_id": account.id,
            "email": account.email,
            "dataset_api_key": dataset_api_key,
            "status": tenant.status,
            "create_at": str(tenant.created_at),
        }, 200

    @staticmethod
    def clear_tenant(tenant_id: str):
        tenant = TenantService.get_tenant_creater(tenant_id)
        creater = TenantService.get_tenant_creater(tenant_id)
        try:
            if tenant:

                # 删除所有默认模型
                default_models = (
                    db.session.query(TenantDefaultModel)
                    .filter(TenantDefaultModel.tenant_id == tenant_id)
                    .all()
                )
                for default_model in default_models:
                    db.session.delete(default_model)

                # 删除所有模型
                models = (
                    db.session.query(ProviderModel)
                    .filter(ProviderModel.tenant_id == tenant_id)
                    .all()
                )
                for model in models:
                    db.session.delete(model)

                db.session.commit()

                TenantService.dissolve_tenant(tenant, creater)
        except Exception as e:
            print(e)
        return False

    @staticmethod
    def create_dataset_api_key(tenant_id: str):
        # The role of the current user in the ta table must be admin or owner

        # current_key_count = db.session.query(ApiToken). \
        #     filter(ApiToken.type == cls.resource_type, ApiToken.tenant_id == tenant_id). \
        #     count()

        # if current_key_count >= self.max_keys:
        #     flask_restful.abort(
        #         400,
        #         message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
        #         code='max_keys_exceeded'
        #     )

        return TenantManage.create_api_key(
            tenant_id,
            TenantManage.data_set_token_prefix,
            TenantManage.data_set_resource_type,
        )

    @staticmethod
    def create_app_api_key(tenant_id: str):
        # The role of the current user in the ta table must be admin or owner

        # current_key_count = db.session.query(ApiToken). \
        #     filter(ApiToken.type == cls.resource_type, ApiToken.tenant_id == tenant_id). \
        #     count()

        # if current_key_count >= self.max_keys:
        #     flask_restful.abort(
        #         400,
        #         message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
        #         code='max_keys_exceeded'
        #     )

        return TenantManage.create_api_key(
            tenant_id, TenantManage.app_token_prefix, TenantManage.app_resource_type
        )

    @staticmethod
    def create_api_key(tenant_id: str, token_prefix: str, resource_type: str):

        key = ApiToken.generate_api_key(token_prefix, 24)
        api_token = ApiToken()
        api_token.tenant_id = tenant_id
        api_token.token = key
        api_token.type = resource_type
        db.session.add(api_token)
        db.session.commit()
        return key


class RAGModelProviderModelParameterRuleApi(DatasetApiResource):

    def get(self, tenant_id, provider: str):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "model", type=str, required=True, nullable=False, location="args"
        )
        args = parser.parse_args()

        # tenant_id = current_user.current_tenant_id

        model_provider_service = ModelProviderService()
        parameter_rules = model_provider_service.get_model_parameter_rules(
            tenant_id=tenant_id, provider=provider, model=args["model"]
        )

        return jsonable_encoder({"data": parameter_rules})


api.add_resource(
    RAGModelProviderModelParameterRuleApi,
    "/dreamcloud/model-providers/<string:provider>/models/parameter-rules",
)

api.add_resource(TenantManage, "/dreamcloud/tenant/create")
# api.add_resource(TenantManage, '/dreamcloud/tenant/<string:tenant_id>/delete')
