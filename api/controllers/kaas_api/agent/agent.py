from flask import json, request,current_app
from flask_restful import Resource, marshal_with, reqparse,fields
from controllers.console.app.app import ALLOW_CREATE_APP_MODES
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.kaas_api.wraps import validate_dream_ai_token
from controllers.service_api.app.error import AppUnavailableError
from core.agent.entities import AgentToolEntity
from core.tools.tool_manager import ToolManager
from core.tools.utils.configuration import ToolParameterConfigurationManager
from models.dataset import AppDatasetJoin
from services.app_model_config_service import AppModelConfigService
from services.app_service import AppService
from events.app_event import app_model_config_was_updated


from libs.helper import TimestampField
from extensions.ext_database import db
from models.model import AppModelConfig,App, AppMode
from controllers.kaas_api import api
from libs.login import current_user, kaas_login_required
from werkzeug.exceptions import BadRequest, Forbidden

from fields.app_fields import (
    related_app_list,
    app_detail_fields_with_site,
)


class CreateAppApi(Resource):
    @setup_required
    @kaas_login_required
    @marshal_with(related_app_list)
    @validate_dream_ai_token(funcs={'and':["kaas:agent"]})
    def get(self):
        tenant_id = str(current_user.current_tenant_id)
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

    @setup_required
    @kaas_login_required
    @validate_dream_ai_token(funcs={'and':["kaas:agent"]})
    @marshal_with(app_detail_fields_with_site)
    def post(self):
        tenant_id = str(current_user.current_tenant_id)
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


class RAGAppInfoApi(Resource):

    @setup_required
    @kaas_login_required
    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def get(self, app_model):
        """Get app detail"""
        app_service = AppService()

        app_model = app_service.get_app(app_model)

        return app_model

    @setup_required
    @kaas_login_required
    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def put(self, app_model):
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

    @setup_required
    @kaas_login_required
    @get_app_model
    def delete(self, app_model):
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


class RAGModelConfigResource(Resource):

    @setup_required
    @kaas_login_required
    @get_app_model(mode=[AppMode.AGENT_CHAT, AppMode.CHAT, AppMode.COMPLETION])
    def post(self, app_model: AppMode):
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


class KaaSAppParameterApi(Resource):
    """Resource for app variables."""

    variable_fields = {
        'key': fields.String,
        'name': fields.String,
        'description': fields.String,
        'type': fields.String,
        'default': fields.String,
        'max_length': fields.Integer,
        'options': fields.List(fields.String)
    }

    system_parameters_fields = {
        'image_file_size_limit': fields.String
    }

    parameters_fields = {
        'opening_statement': fields.String,
        'suggested_questions': fields.Raw,
        'suggested_questions_after_answer': fields.Raw,
        'speech_to_text': fields.Raw,
        'text_to_speech': fields.Raw,
        'retriever_resource': fields.Raw,
        'annotation_reply': fields.Raw,
        'more_like_this': fields.Raw,
        'user_input_form': fields.Raw,
        'sensitive_word_avoidance': fields.Raw,
        'file_upload': fields.Raw,
        'system_parameters': fields.Nested(system_parameters_fields)
    }

    @setup_required
    @kaas_login_required
    @get_app_model
    @marshal_with(parameters_fields)
    def get(self,app_model:App):
        
        if app_model is None:
            raise AppUnavailableError()
        """Retrieve app parameters."""
        if app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
            workflow = app_model.workflow
            if workflow is None:
                raise AppUnavailableError()

            features_dict = workflow.features_dict
            user_input_form = workflow.user_input_form(to_old_structure=True)
        else:
            app_model_config = app_model.app_model_config
            features_dict = app_model_config.to_dict()

            user_input_form = features_dict.get('user_input_form', [])

        return {
            'opening_statement': features_dict.get('opening_statement'),
            'suggested_questions': features_dict.get('suggested_questions', []),
            'suggested_questions_after_answer': features_dict.get('suggested_questions_after_answer',
                                                                  {"enabled": False}),
            'speech_to_text': features_dict.get('speech_to_text', {"enabled": False}),
            'text_to_speech': features_dict.get('text_to_speech', {"enabled": False}),
            'retriever_resource': features_dict.get('retriever_resource', {"enabled": False}),
            'annotation_reply': features_dict.get('annotation_reply', {"enabled": False}),
            'more_like_this': features_dict.get('more_like_this', {"enabled": False}),
            'user_input_form': user_input_form,
            'sensitive_word_avoidance': features_dict.get('sensitive_word_avoidance',
                                                          {"enabled": False, "type": "", "configs": []}),
            'file_upload': features_dict.get('file_upload', {"image": {
                                                     "enabled": False,
                                                     "number_limits": 3,
                                                     "detail": "high",
                                                     "transfer_methods": ["remote_url", "local_file"]
                                                 }}),
            'system_parameters': {
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')
            }
        }

class KaaSAppMetaApi(Resource):
    @setup_required
    @kaas_login_required
    @get_app_model
    def get(self, app_model: App):
        """Get app meta"""
        return AppService().get_app_meta(app_model)

class KaaSAppInfoApi(Resource):
    @setup_required
    @kaas_login_required
    @get_app_model
    def get(self, app_model: App):
        """Get app infomation"""
        return {
            'name':app_model.name,
            'description':app_model.description
        }   

api_key_fields = {
    "id": fields.String,
    "type": fields.String,
    "token": fields.String,
    "last_used_at": TimestampField,
    "created_at": TimestampField,
}

api_key_list = {"data": fields.List(fields.Nested(api_key_fields), attribute="items")}


# def _get_resource(resource_id, tenant_id, resource_model):
#     resource = resource_model.query.filter_by(
#         id=resource_id, tenant_id=tenant_id
#     ).first()

#     if resource is None:
#         flask_restful.abort(404, message=f"{resource_model.__name__} not found.")

#     return resource


# post:创建机器人，get:获取机器人列表
api.add_resource(CreateAppApi, "/agent/apps")
# put:修改机器人，delete:删除机器人，get:获取机器人详情
api.add_resource(RAGAppInfoApi, "/agent/apps/<uuid:app_id>")
# post:配置机器人
api.add_resource(RAGModelConfigResource, "/agent/apps/<uuid:app_id>/model-config")
api.add_resource(KaaSAppParameterApi,"/agent/apps/<uuid:app_id>/parameters")
api.add_resource(KaaSAppMetaApi, '/agent/apps/<uuid:app_id>/meta')
api.add_resource(KaaSAppInfoApi, '/agent/apps/<uuid:app_id>/info')