import json

from flask import request
from flask_login import current_user
from flask_restful import Resource,reqparse
from services.dc_question_service import QuestionService
from controllers.console import api
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.agent.entities import AgentToolEntity
from core.tools.tool_manager import ToolManager
from core.tools.utils.configuration import ToolParameterConfigurationManager
from events.app_event import app_model_config_was_updated
from extensions.ext_database import db
from libs.login import login_required
from models.dc_models import AppQuestions
from models.model import App, AppMode, AppModelConfig
from services.app_model_config_service import AppModelConfigService
from werkzeug.exceptions import NotFound

class ModelConfigResource(Resource):

    @staticmethod
    def _get_app(app_id, mode=None):
        app = db.session.query(App).filter(
        App.id == app_id,
        App.tenant_id == current_user.current_tenant_id,
        App.status == 'normal'
    ).first()

        if not app:
            raise NotFound("App not found")

        if mode and app.mode != mode:
            raise NotFound("The {} app not found".format(mode))

        return app
    @staticmethod
# 查询app——questions对象，如果没有，返回一个新对象
    def _get_app_questions(app_id):
        app_questions = db.session.query(AppQuestions).filter(
            AppQuestions.app_id == app_id,
        ).first()

        if app_questions is None:
            app_questions = AppQuestions(
                app_id = app_id,
            )
        return app_questions

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.AGENT_CHAT, AppMode.CHAT, AppMode.COMPLETION])
    def post(self, app_model):
        """Modify app model config"""

#------------------------------------------------------------
        app_id = app_model.id
        app = ModelConfigResource._get_app(app_id)
        parser = reqparse.RequestParser()
        parser.add_argument('setting', type=dict, location='json')
        args = parser.parse_args()

        functionSettings = args['setting']
        if functionSettings is not None:
            if 'cmd' in functionSettings:
                app.cmd = functionSettings['cmd']
            if 'category' in functionSettings:
                app.category = functionSettings['category']
            if 'func_name' in functionSettings:
                app.func_name = functionSettings['func_name']
            if 'is_robot' in functionSettings:
                app.is_robot = functionSettings['is_robot']
            if 'chat_icon' in functionSettings:
                app.chat_icon = functionSettings['chat_icon']

            # 保存问题列表            
            if 'match_list' in functionSettings:
                fun_match_list= functionSettings['match_list']
                if fun_match_list is not None:
                    QuestionService.update_app_question(tenant_id=current_user.current_tenant_id,questions=fun_match_list,app_id=app_id)
                    # app_questions = ModelConfigResource._get_app_questions(app_id)
                    # if isinstance(fun_match_list,list):
                    #     question_str = '\n'.join(fun_match_list)
                    # else:
                    #     question_str = fun_match_list
                    # if question_str:
                    #     app_questions.questions = question_str
                    #     db.session.add(app_questions)
        
#------------------------------------------------------------
#         
        # validate config
        model_configuration = AppModelConfigService.validate_configuration(
            tenant_id=current_user.current_tenant_id,
            config=request.json,
            app_mode=AppMode.value_of(app_model.mode)
        )

        new_app_model_config = AppModelConfig(
            app_id=app_model.id,
        )
        new_app_model_config = new_app_model_config.from_model_config_dict(model_configuration)

        if app_model.mode == AppMode.AGENT_CHAT.value or app_model.is_agent:
            # get original app model config
            original_app_model_config: AppModelConfig = db.session.query(AppModelConfig).filter(
                AppModelConfig.id == app_model.app_model_config_id
            ).first()
            agent_mode = original_app_model_config.agent_mode_dict
            # decrypt agent tool parameters if it's secret-input
            parameter_map = {}
            masked_parameter_map = {}
            tool_map = {}
            for tool in agent_mode.get('tools') or []:
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
                        identity_id=f'AGENT.{app_model.id}'
                    )
                except Exception as e:
                    continue

                # get decrypted parameters
                if agent_tool_entity.tool_parameters:
                    parameters = manager.decrypt_tool_parameters(agent_tool_entity.tool_parameters or {})
                    masked_parameter = manager.mask_tool_parameters(parameters or {})
                else:
                    parameters = {}
                    masked_parameter = {}

                key = f'{agent_tool_entity.provider_id}.{agent_tool_entity.provider_type}.{agent_tool_entity.tool_name}'
                masked_parameter_map[key] = masked_parameter
                parameter_map[key] = parameters
                tool_map[key] = tool_runtime

            # encrypt agent tool parameters if it's secret-input
            agent_mode = new_app_model_config.agent_mode_dict
            for tool in agent_mode.get('tools') or []:
                agent_tool_entity = AgentToolEntity(**tool)

                # get tool
                key = f'{agent_tool_entity.provider_id}.{agent_tool_entity.provider_type}.{agent_tool_entity.tool_name}'
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
                    identity_id=f'AGENT.{app_model.id}'
                )
                manager.delete_tool_parameters_cache()

                # override parameters if it equals to masked parameters
                if agent_tool_entity.tool_parameters:
                    if key not in masked_parameter_map:
                        continue
                    
                    for masked_key, masked_value in masked_parameter_map[key].items():
                        if masked_key in agent_tool_entity.tool_parameters and \
                                agent_tool_entity.tool_parameters[masked_key] == masked_value:
                            agent_tool_entity.tool_parameters[masked_key] = parameter_map[key].get(masked_key)

                # encrypt parameters
                if agent_tool_entity.tool_parameters:
                    tool['tool_parameters'] = manager.encrypt_tool_parameters(agent_tool_entity.tool_parameters or {})

            # update app model config
            new_app_model_config.agent_mode = json.dumps(agent_mode)

        db.session.add(new_app_model_config)
        db.session.flush()

        app_model.app_model_config_id = new_app_model_config.id
        db.session.commit()

        app_model_config_was_updated.send(
            app_model,
            app_model_config=new_app_model_config
        )

        return {'result': 'success'}


api.add_resource(ModelConfigResource, '/apps/<uuid:app_id>/model-config')
