import json
from collections.abc import Generator
from typing import Any, Union

from sqlalchemy import and_
from sqlalchemy.orm import aliased

# from core.application_manager import ApplicationManager
# from core.deram_application_manager import DeramApplicationManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.file.message_file_parser import MessageFileParser
from extensions.ext_database import db
from models.dc_models import AppCategory, AppQuestions
from models.model import Account, App, AppModelConfig, Conversation, EndUser, Message,Site
from services.app_model_config_service import AppModelConfigService
from services.errors.app import MoreLikeThisDisabledError
from services.errors.app_model_config import AppModelConfigBrokenError
from services.errors.conversation import ConversationCompletedError, ConversationNotExistsError
from services.errors.message import MessageNotExistsError
from datetime import datetime


class ChatRebotService:
    @classmethod
    def get_cmd_app(cls,cmd:str):
        app_model = db.session.query(App).filter(App.cmd == cmd).first()
        if not app_model:
            return None

        if app_model.status != 'normal':
            return None

        if not app_model.enable_api:
            return None
        return app_model
    
    @classmethod
    def get_app_categories(cls)->list:
        categories = db.session.query(AppCategory).filter(AppCategory.is_del==False).all()
        return categories
    
    #select a.id as app_id,a.name as app_name,a.cmd as cmd,a.category as category,a.func_name as func_name,b.description as desc from apps as a  join sites as b on a.id=b.app_id where cmd is not null
    @classmethod
    def get_cmds(cls)->dict:
        aa = cls.get_app_categories()
        # app_id = aliased(App.id).alias('app_id')
        # app_name = aliased(App.name).alias('app_name')
        cmds = db.session.query(App.id.label('app_id'),App.name.label('app_name'),\
                                App.chat_icon,\
                         App.cmd,App.category,App.category_name,App.func_name,Site.description).\
                         join(Site,Site.app_id==App.id).filter(App.cmd !=None, App.cmd!="").all()
        ret :dict = {"categories":[]}
        if cmds is not None:
            for cmd in cmds:
                # if cmd.category in ret['categories']:
                if  any(d['id'] == cmd.category for d in ret["categories"]):
                    item = [d for d in ret["categories"] if d['id']==cmd.category][0]
                    que_list = cls.get_question_list(cmd)
                    cmd_dict = cmd._asdict()
                    cmd_dict["questions"]=que_list
                    item["cmds"].append(cmd_dict)
                    # ret["categories"]["cmds"].append(cmd._asdict())
                else:
                    que_list = cls.get_question_list(cmd)
                    cmd_dict = cmd._asdict()
                    cmd_dict["questions"]=que_list
                    ret["categories"].append({"id":cmd.category,"name":cmd.category_name,"cmds":[cmd_dict]}) 
        return ret

    @classmethod
    def get_question_list(cls, cmd):
        questions = db.session.query(AppQuestions.questions).filter(AppQuestions.app_id==cmd.app_id).first()
        if questions.questions is None or len(questions.questions)==0:
            return None
        que_list  = [que for  que in questions.questions.split('\n')]
        
        return que_list #if que_list is not None and len(que_list)>0 else None

    @classmethod
    def get_tenant_token_consume(cls,app_token:str,begTime:datetime,endTime:datetime) -> dict:
        end_user_id = db.session.query(EndUser.id).filter(EndUser.app_token==app_token).first()

        ret = db.session.query(db.func.sum(Message.message_tokens).label('total_message_tokens'),\
                         db.func.sum(Message.answer_tokens).label('total_answer_tokens'),\
                        db.func.sum(Message.provider_response_latency).label('total_latency')).\
                        filter(Message.from_end_user_id==end_user_id.id,\
                              Message.created_at > begTime,\
                            Message.created_at < endTime ).first()

        return ret._asdict()
    
    @classmethod
    def chat3(cls, app_model: App, user: Union[Account, EndUser], args: Any,
                   invoke_from: InvokeFrom, streaming: bool = True,
                   is_model_config_override: bool = False) -> Union[dict, Generator]:
        # is streaming mode
        print("进入=>>api.service.chat_robot_service:","ChatRebotService::chat")
        inputs = args['inputs']
        query = args['query']
        cmd = args['cmd']
        files = args['files'] if 'files' in args and args['files'] else []
        app_model_id = app_model.id
        if cmd:    
            app_model = cls.get_cmd_app(cmd)

            
        
        auto_generate_name = args['auto_generate_name'] \
            if 'auto_generate_name' in args else True

        if app_model.mode != 'completion':
            if not query:
                raise ValueError('query is required')

        if query:
            if not isinstance(query, str):
                raise ValueError('query must be a string')

            query = query.replace('\x00', '')

        conversation_id = args['conversation_id'] if 'conversation_id' in args else None

        conversation = None
        if conversation_id:
            conversation_filter = [
                Conversation.id == args['conversation_id'],
                Conversation.app_id == app_model_id,#app_model.id,
                Conversation.status == 'normal'
            ]

            if isinstance(user, Account):
                conversation_filter.append(Conversation.from_account_id == user.id)
            else:
                conversation_filter.append(Conversation.from_end_user_id == user.id if user else None)

            conversation = db.session.query(Conversation).filter(and_(*conversation_filter)).first()

            if not conversation:
                raise ConversationNotExistsError()

            if conversation.status != 'normal':
                raise ConversationCompletedError()

            # select distinct on (app_id) * from app_model_configs where app_id='3dcd5319-690e-45f4-af9b-6a0e96129870' order by app_id, updated_at desc
            if not conversation.override_model_configs:
                app_model_config = db.session.query(AppModelConfig).filter(
                    AppModelConfig.id == app_model.app_model_config_id# conversation.app_model_config_id,
                    # AppModelConfig.app_id ==  app_model.id
                ).first()

                if not app_model_config:
                    raise AppModelConfigBrokenError()
            else:
                conversation_override_model_configs = json.loads(conversation.override_model_configs)

                app_model_config = AppModelConfig(
                    id=conversation.app_model_config_id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(conversation_override_model_configs)
            
            if is_model_config_override:
                # build new app model config
                if 'model' not in args['model_config']:
                    raise ValueError('model_config.model is required')

                if 'completion_params' not in args['model_config']['model']:
                    raise ValueError('model_config.model.completion_params is required')

                completion_params = AppModelConfigService.validate_model_completion_params(
                    cp=args['model_config']['model']['completion_params'],
                    model_name=app_model_config.model_dict["name"]
                )

                app_model_config_model = app_model_config.model_dict
                app_model_config_model['completion_params'] = completion_params
                app_model_config.retriever_resource = json.dumps({'enabled': True})

                app_model_config = app_model_config.copy()
                app_model_config.model = json.dumps(app_model_config_model)
        else:
            if app_model.app_model_config_id is None:
                raise AppModelConfigBrokenError()

            app_model_config = app_model.app_model_config

            if not app_model_config:
                raise AppModelConfigBrokenError()

            if is_model_config_override:
                if not isinstance(user, Account):
                    raise Exception("Only account can override model config")

                # validate config
                model_config = AppModelConfigService.validate_configuration(
                    tenant_id=app_model.tenant_id,
                    account=user,
                    config=args['model_config'],
                    app_mode=app_model.mode
                )

                app_model_config = AppModelConfig(
                    id=app_model_config.id,
                    app_id=app_model_id,#app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(model_config)

        # clean input by app_model_config form rules
        inputs = cls.get_cleaned_inputs(inputs, app_model_config)

        # parse files
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.validate_and_transform_files_arg(
            files,
            app_model_config,
            user
        )
        print("获取 用户 用户输入变量 文件列表 Converstion对象 app_model_config对象")

        application_manager = DeramApplicationManager()
        print("退出<<=/api/service/sompletion_service:","CompletionService::completion","返回application_manager.generate生成器")

        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=is_model_config_override,
            user=user,
            invoke_from=invoke_from,
            inputs=inputs,
            query=query,
            files=file_objs,
            conversation=conversation,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": auto_generate_name
            },
            cmd = cmd
        )
    
    @classmethod
    def chat2(cls, app_model: App, user: Union[Account, EndUser], args: Any,
                   invoke_from: InvokeFrom, rouyi_user_id:str,streaming: bool = True,
                   is_model_config_override: bool = False) -> Union[dict, Generator]:
        # is streaming mode
        print("进入=>>api.service.chat_robot_service:","ChatRebotService::chat")
        inputs = args['inputs']
        query = args['query']
        cmd = args['cmd']
        files = args['files'] if 'files' in args and args['files'] else []
        app_model_id = app_model.id
        if cmd:    
            app_model = cls.get_cmd_app(cmd)

            
        
        auto_generate_name = args['auto_generate_name'] \
            if 'auto_generate_name' in args else True

        if app_model.mode != 'completion':
            if not query:
                raise ValueError('query is required')

        if query:
            if not isinstance(query, str):
                raise ValueError('query must be a string')

            query = query.replace('\x00', '')

        conversation_id = args['conversation_id'] if 'conversation_id' in args else None

        conversation = None
        if conversation_id:
            conversation_filter = [
                Conversation.id == args['conversation_id'],
                Conversation.app_id == app_model_id,#app_model.id,
                Conversation.status == 'normal'
            ]

            if isinstance(user, Account):
                conversation_filter.append(Conversation.from_account_id == user.id)
            else:
                conversation_filter.append(Conversation.from_end_user_id == user.id if user else None)

            conversation = db.session.query(Conversation).filter(and_(*conversation_filter)).first()

            if not conversation:
                raise ConversationNotExistsError()

            if conversation.status != 'normal':
                raise ConversationCompletedError()

            # select distinct on (app_id) * from app_model_configs where app_id='3dcd5319-690e-45f4-af9b-6a0e96129870' order by app_id, updated_at desc
            if not conversation.override_model_configs:
                app_model_config = db.session.query(AppModelConfig).filter(
                    # AppModelConfig.id == conversation.app_model_config_id,
                    AppModelConfig.app_id ==  app_model.id
                ).first()

                if not app_model_config:
                    raise AppModelConfigBrokenError()
            else:
                conversation_override_model_configs = json.loads(conversation.override_model_configs)

                app_model_config = AppModelConfig(
                    id=conversation.app_model_config_id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(conversation_override_model_configs)
            
            if is_model_config_override:
                # build new app model config
                if 'model' not in args['model_config']:
                    raise ValueError('model_config.model is required')

                if 'completion_params' not in args['model_config']['model']:
                    raise ValueError('model_config.model.completion_params is required')

                completion_params = AppModelConfigService.validate_model_completion_params(
                    cp=args['model_config']['model']['completion_params'],
                    model_name=app_model_config.model_dict["name"]
                )

                app_model_config_model = app_model_config.model_dict
                app_model_config_model['completion_params'] = completion_params
                app_model_config.retriever_resource = json.dumps({'enabled': True})

                app_model_config = app_model_config.copy()
                app_model_config.model = json.dumps(app_model_config_model)
        else:
            if app_model.app_model_config_id is None:
                raise AppModelConfigBrokenError()

            app_model_config = app_model.app_model_config

            if not app_model_config:
                raise AppModelConfigBrokenError()

            if is_model_config_override:
                if not isinstance(user, Account):
                    raise Exception("Only account can override model config")

                # validate config
                model_config = AppModelConfigService.validate_configuration(
                    tenant_id=app_model.tenant_id,
                    account=user,
                    config=args['model_config'],
                    app_mode=app_model.mode
                )

                app_model_config = AppModelConfig(
                    id=app_model_config.id,
                    app_id=app_model_id,#app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(model_config)

        # clean input by app_model_config form rules
        inputs = cls.get_cleaned_inputs(inputs, app_model_config)

        # parse files
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.validate_and_transform_files_arg(
            files,
            app_model_config,
            user
        )
        print("获取 用户 用户输入变量 文件列表 Converstion对象 app_model_config对象")

        application_manager = ApplicationManager()
        print("退出<<=/api/service/sompletion_service:","CompletionService::completion","返回application_manager.generate生成器")

        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=is_model_config_override,
            user=user,
            invoke_from=invoke_from,
            inputs=inputs,
            query=query,
            files=file_objs,
            conversation=conversation,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": auto_generate_name
            }
        )
    

    


    @classmethod
    def chat(cls, app_model: App, user: Union[Account, EndUser], args: Any,
                   invoke_from: InvokeFrom, rouyi_user_id:str,streaming: bool = True,
                   is_model_config_override: bool = False) -> Union[dict, Generator]:
        # is streaming mode
        print("进入=>>api.service.chat_robot_service:","ChatRebotService::chat")
        inputs = args['inputs']
        query = args['query']
        cmd = args['cmd']
        files = args['files'] if 'files' in args and args['files'] else []
        
        auto_generate_name = args['auto_generate_name'] \
            if 'auto_generate_name' in args else True

        if app_model.mode != 'completion':
            if not query:
                raise ValueError('query is required')

        if query:
            if not isinstance(query, str):
                raise ValueError('query must be a string')

            query = query.replace('\x00', '')

        conversation_id = args['conversation_id'] if 'conversation_id' in args else None

        conversation = None
        if conversation_id:
            conversation_filter = [
                Conversation.id == args['conversation_id'],
                Conversation.app_id == app_model.id,
                Conversation.status == 'normal'
            ]

            if isinstance(user, Account):
                conversation_filter.append(Conversation.from_account_id == user.id)
            else:
                conversation_filter.append(Conversation.from_end_user_id == user.id if user else None)

            conversation = db.session.query(Conversation).filter(and_(*conversation_filter)).first()

            if not conversation:
                raise ConversationNotExistsError()

            if conversation.status != 'normal':
                raise ConversationCompletedError()

            if not conversation.override_model_configs:
                app_model_config = db.session.query(AppModelConfig).filter(
                    AppModelConfig.id == conversation.app_model_config_id,
                    AppModelConfig.app_id == app_model.id
                ).first()

                if not app_model_config:
                    raise AppModelConfigBrokenError()
            else:
                conversation_override_model_configs = json.loads(conversation.override_model_configs)

                app_model_config = AppModelConfig(
                    id=conversation.app_model_config_id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(conversation_override_model_configs)
            
            if is_model_config_override:
                # build new app model config
                if 'model' not in args['model_config']:
                    raise ValueError('model_config.model is required')

                if 'completion_params' not in args['model_config']['model']:
                    raise ValueError('model_config.model.completion_params is required')

                completion_params = AppModelConfigService.validate_model_completion_params(
                    cp=args['model_config']['model']['completion_params'],
                    model_name=app_model_config.model_dict["name"]
                )

                app_model_config_model = app_model_config.model_dict
                app_model_config_model['completion_params'] = completion_params
                app_model_config.retriever_resource = json.dumps({'enabled': True})

                app_model_config = app_model_config.copy()
                app_model_config.model = json.dumps(app_model_config_model)
        else:
            if app_model.app_model_config_id is None:
                raise AppModelConfigBrokenError()

            app_model_config = app_model.app_model_config

            if not app_model_config:
                raise AppModelConfigBrokenError()

            if is_model_config_override:
                if not isinstance(user, Account):
                    raise Exception("Only account can override model config")

                # validate config
                model_config = AppModelConfigService.validate_configuration(
                    tenant_id=app_model.tenant_id,
                    account=user,
                    config=args['model_config'],
                    app_mode=app_model.mode
                )

                app_model_config = AppModelConfig(
                    id=app_model_config.id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(model_config)

        # clean input by app_model_config form rules
        inputs = cls.get_cleaned_inputs(inputs, app_model_config)

        # parse files
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.validate_and_transform_files_arg(
            files,
            app_model_config,
            user
        )
        print("获取 用户 用户输入变量 文件列表 Converstion对象 app_model_config对象")

        application_manager = ApplicationManager()
        print("退出<<=/api/service/sompletion_service:","CompletionService::completion","返回application_manager.generate生成器")
        #--------------------------------------------------------------------
        if cmd:
            cmdApp = cls.get_cmd_app(cmd)
            if cmdApp:
                if cmdApp.mode == 'completion' or cmdApp.mode == 'chat':
                    app_model_config = cmdApp.app_model_config 
                    return application_manager.generate(
                            tenant_id=cmdApp.tenant_id,
                            app_id=cmdApp.id,
                            app_model_config_id=app_model_config.id,
                            app_model_config_dict=app_model_config.to_dict(),
                            app_model_config_override=is_model_config_override,
                            user=user,
                            invoke_from=invoke_from,
                            inputs=inputs,
                            query=query,
                            files=file_objs,
                            conversation=None,# conversation,
                            stream=streaming,
                            extras={
                                "auto_generate_conversation_name": auto_generate_name
                            }
                    )
        #--------------------------------------------------------------------
        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=is_model_config_override,
            user=user,
            invoke_from=invoke_from,
            inputs=inputs,
            query=query,
            files=file_objs,
            conversation=conversation,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": auto_generate_name
            }
        )

    @classmethod
    def generate_more_like_this(cls, app_model: App, user: Union[Account, EndUser],
                                message_id: str, invoke_from: InvokeFrom, streaming: bool = True) \
            -> Union[dict, Generator]:
        if not user:
            raise ValueError('user cannot be None')

        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id,
            Message.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Message.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Message.from_account_id == (user.id if isinstance(user, Account) else None),
        ).first()

        if not message:
            raise MessageNotExistsError()

        current_app_model_config = app_model.app_model_config
        more_like_this = current_app_model_config.more_like_this_dict

        if not current_app_model_config.more_like_this or more_like_this.get("enabled", False) is False:
            raise MoreLikeThisDisabledError()

        app_model_config = message.app_model_config
        model_dict = app_model_config.model_dict
        completion_params = model_dict.get('completion_params')
        completion_params['temperature'] = 0.9
        model_dict['completion_params'] = completion_params
        app_model_config.model = json.dumps(model_dict)

        # parse files
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.transform_message_files(
            message.files, app_model_config
        )

        application_manager = ApplicationManager()
        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=True,
            user=user,
            invoke_from=invoke_from,
            inputs=message.inputs,
            query=message.query,
            files=file_objs,
            conversation=None,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": False
            }
        )

    @classmethod
    def get_cleaned_inputs(cls, user_inputs: dict, app_model_config: AppModelConfig):
        if user_inputs is None:
            user_inputs = {}

        filtered_inputs = {}

        # Filter input variables from form configuration, handle required fields, default values, and option values
        input_form_config = app_model_config.user_input_form_list
        for config in input_form_config:
            input_config = list(config.values())[0]
            variable = input_config["variable"]

            input_type = list(config.keys())[0]

            if variable not in user_inputs or not user_inputs[variable]:
                if input_type == "external_data_tool":
                    continue
                if "required" in input_config and input_config["required"]:
                    raise ValueError(f"{variable} is required in input form")
                else:
                    filtered_inputs[variable] = input_config["default"] if "default" in input_config else ""
                    continue

            value = user_inputs[variable]

            if value:
                if not isinstance(value, str):
                    raise ValueError(f"{variable} in input form must be a string")

            if input_type == "select":
                options = input_config["options"] if "options" in input_config else []
                if value not in options:
                    raise ValueError(f"{variable} in input form must be one of the following: {options}")
            else:
                if 'max_length' in input_config:
                    max_length = input_config['max_length']
                    if len(value) > max_length:
                        raise ValueError(f'{variable} in input form must be less than {max_length} characters')

            filtered_inputs[variable] = value.replace('\x00', '') if value else None

        return filtered_inputs
