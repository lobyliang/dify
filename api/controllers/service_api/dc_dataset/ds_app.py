from flask import request
from flask_restful import marshal_with, reqparse
import flask_restful
from controllers.console.app.app import ALLOW_CREATE_APP_MODES
from controllers.console.app.wraps import get_app_model
from models.dataset import AppDatasetJoin
from services.app_service import AppService


from flask import json, request
from flask_restful import fields, reqparse
from libs.helper import TimestampField
from extensions.ext_database import db
from models.model import ApiToken
from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource
from libs.login import current_user
from werkzeug.exceptions import Forbidden
from extensions.ext_database import db
from models.model import App, AppMode
from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource
from libs.login import current_user
from werkzeug.exceptions import Forbidden
from werkzeug.exceptions import BadRequest, Forbidden

from fields.app_fields import (
    related_app_list,
    app_detail_fields_with_site,
)
import json

from flask import request
from flask_login import current_user

from controllers.console.app.wraps import get_app_model
from core.agent.entities import AgentToolEntity
from core.tools.tool_manager import ToolManager
from core.tools.utils.configuration import ToolParameterConfigurationManager
from events.app_event import app_model_config_was_updated
from extensions.ext_database import db
from models.model import AppMode, AppModelConfig
from services.app_model_config_service import AppModelConfigService


class CreateAppApi(DatasetApiResource):
    @marshal_with(related_app_list)
    def get(self, tenant_id):
        argparser = reqparse.RequestParser()
        argparser.add_argument(
            "mode", type=AppMode, location="args", required=False, default=None
        )
        args = argparser.parse_args()
        mode = args.get("mode")
        try:
            query = db.session.query(App).filter(App.tenant_id == tenant_id)
            if mode:
                query = query.filter(App.mode == mode)
            apps = query.all()
        except Exception as e:
            raise BadRequest(str(e))
        return {"data": apps, "total": len(apps)}, 200

    @marshal_with(app_detail_fields_with_site)
    def post(self, tenant_id):
        """Create app"""
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True, location="json")
        parser.add_argument("description", type=str, location="json")
        parser.add_argument(
            "mode", type=str, choices=ALLOW_CREATE_APP_MODES, location="json"
        )
        parser.add_argument("icon", type=str, location="json")
        parser.add_argument("icon_background", type=str, location="json")
        args = parser.parse_args()

        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        if "mode" not in args or args["mode"] is None:
            raise BadRequest("mode is required")

        app_service = AppService()
        app = app_service.create_app(tenant_id, args, current_user)

        return app, 201


class RAGAppInfoApi(DatasetApiResource):

    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def get(self, tenant_id, app_model):
        """Get app detail"""
        # if not app_id:
        #     raise ValueError('missing app_id in path parameters')

        # app_model = db.session.query(App).filter(
        #     App.id == app_id,
        #     App.tenant_id == tenant_id,
        #     App.status == 'normal'
        # ).first()

        # if not app_model:
        #     raise AppNotFoundError()

        # app_mode = AppMode.value_of(app_model.mode)
        # if app_mode == AppMode.CHANNEL:
        #     raise AppNotFoundError()

        # if mode is not None:
        #     if isinstance(mode, list):
        #         modes = mode
        #     else:
        #         modes = [mode]

        #     if app_mode not in modes:
        #         mode_values = {m.value for m in modes}
        #         raise AppNotFoundError(f"App mode is not in the supported list: {mode_values}")

        ############lobyliang############33
        app_service = AppService()

        app_model = app_service.get_app(app_model)

        return app_model

    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def put(self, tenant_id, app_model):
        """Update app"""
        parser = reqparse.RequestParser()
        parser.add_argument(
            "name", type=str, required=True, nullable=False, location="json"
        )
        parser.add_argument("description", type=str, location="json")
        parser.add_argument("icon", type=str, location="json")
        parser.add_argument("icon_background", type=str, location="json")
        args = parser.parse_args()

        app_service = AppService()
        app_model = app_service.update_app(app_model, args)

        return app_model

    @get_app_model
    def delete(self, tenant_id, app_model):
        """Delete app"""
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_service = AppService()
        app_service.delete_app(app_model)
        try:
            db.session.query(AppDatasetJoin).filter(
                AppDatasetJoin.app_id == app_model.id
            ).delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {"result": "failed", "message": str(e)}, 400

        return {"result": "success"}, 204


class RAGModelConfigResource(DatasetApiResource):

    @get_app_model(mode=[AppMode.AGENT_CHAT, AppMode.CHAT, AppMode.COMPLETION])
    def post(self, tenant_id, app_model: AppMode):
        """Modify app model config"""
        # validate config
        try:
            model_configuration = AppModelConfigService.validate_configuration(
                tenant_id=current_user.current_tenant_id,
                config=request.json,
                app_mode=AppMode.value_of(app_model.mode),
            )
        except Exception as e:
            raise BadRequest(str(e))

        new_app_model_config = AppModelConfig(
            app_id=app_model.id,
        )
        new_app_model_config = new_app_model_config.from_model_config_dict(
            model_configuration
        )

        if app_model.mode == AppMode.AGENT_CHAT.value or app_model.is_agent:
            # get original app model config
            original_app_model_config: AppModelConfig = (
                db.session.query(AppModelConfig)
                .filter(AppModelConfig.id == app_model.app_model_config_id)
                .first()
            )
            agent_mode = original_app_model_config.agent_mode_dict
            # decrypt agent tool parameters if it's secret-input
            parameter_map = {}
            masked_parameter_map = {}
            tool_map = {}
            for tool in agent_mode.get("tools") or []:
                if not isinstance(tool, dict) or len(tool.keys()) <= 3:
                    continue

                agent_tool_entity = AgentToolEntity(**tool)
                # get tool
                try:
                    tool_runtime = ToolManager.get_agent_tool_runtime(
                        tenant_id=current_user.current_tenant_id,
                        app_id=app_model.id,
                        agent_tool=agent_tool_entity,
                    )
                    manager = ToolParameterConfigurationManager(
                        tenant_id=current_user.current_tenant_id,
                        tool_runtime=tool_runtime,
                        provider_name=agent_tool_entity.provider_id,
                        provider_type=agent_tool_entity.provider_type,
                        identity_id=f"AGENT.{app_model.id}",
                    )
                except Exception as e:
                    continue

                # get decrypted parameters
                if agent_tool_entity.tool_parameters:
                    parameters = manager.decrypt_tool_parameters(
                        agent_tool_entity.tool_parameters or {}
                    )
                    masked_parameter = manager.mask_tool_parameters(parameters or {})
                else:
                    parameters = {}
                    masked_parameter = {}

                key = f"{agent_tool_entity.provider_id}.{agent_tool_entity.provider_type}.{agent_tool_entity.tool_name}"
                masked_parameter_map[key] = masked_parameter
                parameter_map[key] = parameters
                tool_map[key] = tool_runtime

            # encrypt agent tool parameters if it's secret-input
            agent_mode = new_app_model_config.agent_mode_dict
            for tool in agent_mode.get("tools") or []:
                agent_tool_entity = AgentToolEntity(**tool)

                # get tool
                key = f"{agent_tool_entity.provider_id}.{agent_tool_entity.provider_type}.{agent_tool_entity.tool_name}"
                if key in tool_map:
                    tool_runtime = tool_map[key]
                else:
                    try:
                        tool_runtime = ToolManager.get_agent_tool_runtime(
                            tenant_id=current_user.current_tenant_id,
                            app_id=app_model.id,
                            agent_tool=agent_tool_entity,
                        )
                    except Exception as e:
                        continue

                manager = ToolParameterConfigurationManager(
                    tenant_id=current_user.current_tenant_id,
                    tool_runtime=tool_runtime,
                    provider_name=agent_tool_entity.provider_id,
                    provider_type=agent_tool_entity.provider_type,
                    identity_id=f"AGENT.{app_model.id}",
                )
                manager.delete_tool_parameters_cache()

                # override parameters if it equals to masked parameters
                if agent_tool_entity.tool_parameters:
                    if key not in masked_parameter_map:
                        continue

                    for masked_key, masked_value in masked_parameter_map[key].items():
                        if (
                            masked_key in agent_tool_entity.tool_parameters
                            and agent_tool_entity.tool_parameters[masked_key]
                            == masked_value
                        ):
                            agent_tool_entity.tool_parameters[masked_key] = (
                                parameter_map[key].get(masked_key)
                            )

                # encrypt parameters
                if agent_tool_entity.tool_parameters:
                    tool["tool_parameters"] = manager.encrypt_tool_parameters(
                        agent_tool_entity.tool_parameters or {}
                    )

            # update app model config
            new_app_model_config.agent_mode = json.dumps(agent_mode)

        db.session.add(new_app_model_config)
        db.session.flush()

        app_model.app_model_config_id = new_app_model_config.id
        db.session.commit()

        app_model_config_was_updated.send(
            app_model, app_model_config=new_app_model_config
        )

        return {"result": "success"}


api_key_fields = {
    "id": fields.String,
    "type": fields.String,
    "token": fields.String,
    "last_used_at": TimestampField,
    "created_at": TimestampField,
}

api_key_list = {"data": fields.List(fields.Nested(api_key_fields), attribute="items")}


def _get_resource(resource_id, tenant_id, resource_model):
    resource = resource_model.query.filter_by(
        id=resource_id, tenant_id=tenant_id
    ).first()

    if resource is None:
        flask_restful.abort(404, message=f"{resource_model.__name__} not found.")

    return resource


class RAGAppApiKeyListResource(DatasetApiResource):
    # method_decorators = [account_initialization_required, login_required, setup_required]

    def after_request(self, resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    resource_type = "app"
    resource_model = App
    resource_id_field = "app_id"
    token_prefix = "app-"
    max_keys = 10

    @marshal_with(api_key_list)
    def get(self, tenant_id, resource_id):
        resource_id = str(resource_id)
        _get_resource(resource_id, current_user.current_tenant_id, self.resource_model)
        keys = (
            db.session.query(ApiToken)
            .filter(
                ApiToken.type == self.resource_type,
                getattr(ApiToken, self.resource_id_field) == resource_id,
            )
            .all()
        )
        return {"items": keys}

    @marshal_with(api_key_fields)
    def post(self, tenant_id, resource_id):
        resource_id = str(resource_id)
        _get_resource(resource_id, current_user.current_tenant_id, self.resource_model)
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        current_key_count = (
            db.session.query(ApiToken)
            .filter(
                ApiToken.type == self.resource_type,
                getattr(ApiToken, self.resource_id_field) == resource_id,
            )
            .count()
        )

        if current_key_count >= self.max_keys:
            flask_restful.abort(
                400,
                message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
                code="max_keys_exceeded",
            )

        key = ApiToken.generate_api_key(self.token_prefix, 24)
        api_token = ApiToken()
        setattr(api_token, self.resource_id_field, resource_id)
        api_token.tenant_id = current_user.current_tenant_id
        api_token.token = key
        api_token.type = self.resource_type
        db.session.add(api_token)
        db.session.commit()
        return api_token, 201


api.add_resource(CreateAppApi, "/rag/apps")
api.add_resource(RAGAppInfoApi, "/rag/apps/<uuid:app_id>")
api.add_resource(RAGModelConfigResource, "/rag/apps/<uuid:app_id>/model-config")
api.add_resource(RAGAppApiKeyListResource, "/rag/apps/<uuid:resource_id>/api-keys")
