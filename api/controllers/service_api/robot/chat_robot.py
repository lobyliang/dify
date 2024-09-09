import logging
from core.app.apps.base_app_queue_manager import AppQueueManager
from extensions.ext_database import db
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError, NotFound
from libs import helper
from core.app.entities.app_invoke_entities import InvokeFrom
import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    NotChatAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.service_api.wraps import (
    FetchUserArg,
    WhereisUserArg,
    dream_validate_cmd_token,
    validate_app_token,
)

from core.errors.error import (
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.model_runtime.errors.invoke import InvokeError
from libs.helper import uuid_value
from models.model import App, AppMode, EndUser
from services.app_generate_service import AppGenerateService
import services.errors
import services.errors.app_model_config
import services.errors.conversation
from services.dc_question_service import QuestionService

# from services.chat_robot_service import ChatRebotService


# class ChatRobot(Resource):
#     @validate_cmd_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
#     def post(self, app_model: App, end_user: EndUser,):#rouyi_user_id:str):

#         if app_model.mode != 'chat':
#             raise NotChatAppError()

#         parser = reqparse.RequestParser()
#         parser.add_argument('inputs', type=dict, required=True, location='json')
#         parser.add_argument('cmd', type=str, required=False, location='json')
#         parser.add_argument('query', type=str, required=True, location='json')
#         parser.add_argument('files', type=list, required=False, location='json')
#         parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
#         parser.add_argument('conversation_id', type=uuid_value, location='json')
#         parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
#         parser.add_argument('auto_generate_name', type=bool, required=False, default=False, location='json')

#         args = parser.parse_args()

#         streaming = args['response_mode'] == 'streaming'


#         try:
#             response = ChatRebotService.chat(
#                 app_model=app_model,
#                 user=end_user,
#                 args=args,
#                 invoke_from=InvokeFrom.SERVICE_API,
#                 streaming=streaming,
#                 rouyi_user_id = "123"
#             )

#             return compact_response(response)
#         except services.errors.conversation.ConversationNotExistsError:
#             raise NotFound("Conversation Not Exists.")
#         except services.errors.conversation.ConversationCompletedError:
#             raise ConversationCompletedError()
#         except services.errors.app_model_config.AppModelConfigBrokenError:
#             logging.exception("App model config broken.")
#             raise AppUnavailableError()
#         except ProviderTokenNotInitError as ex:
#             raise ProviderNotInitializeError(ex.description)
#         except QuotaExceededError:
#             raise ProviderQuotaExceededError()
#         except ModelCurrentlyNotSupportError:
#             raise ProviderModelCurrentlyNotSupportError()
#         except InvokeError as e:
#             raise CompletionRequestError(e.description)
#         except ValueError as e:
#             raise e
#         except Exception as e:
#             logging.exception("internal server error.")
#             raise InternalServerError()


# class ChatRobot2(Resource):
#     @validate_cmd_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
#     def post(self, app_model: App, end_user: EndUser):

#         if app_model.mode != 'chat':
#             raise NotChatAppError()

#         parser = reqparse.RequestParser()
#         parser.add_argument('inputs', type=dict, required=True, location='json')
#         parser.add_argument('cmd', type=str, required=False, location='json')
#         parser.add_argument('query', type=str, required=True, location='json')
#         parser.add_argument('files', type=list, required=False, location='json')
#         parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
#         parser.add_argument('conversation_id', type=uuid_value, location='json')
#         parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
#         parser.add_argument('auto_generate_name', type=bool, required=False, default=False, location='json')

#         args = parser.parse_args()

#         streaming = args['response_mode'] == 'streaming'


#         try:
#             response = ChatRebotService.chat3(
#                 app_model=app_model,
#                 user=end_user,
#                 args=args,
#                 invoke_from=InvokeFrom.SERVICE_API,
#                 streaming=streaming,
#             )

#             return compact_response(response)
#         except services.errors.conversation.ConversationNotExistsError:
#             raise NotFound("Conversation Not Exists.")
#         except services.errors.conversation.ConversationCompletedError:
#             raise ConversationCompletedError()
#         except services.errors.app_model_config.AppModelConfigBrokenError:
#             logging.exception("App model config broken.")
#             raise AppUnavailableError()
#         except ProviderTokenNotInitError as ex:
#             raise ProviderNotInitializeError(ex.description)
#         except QuotaExceededError:
#             raise ProviderQuotaExceededError()
#         except ModelCurrentlyNotSupportError:
#             raise ProviderModelCurrentlyNotSupportError()
#         except InvokeError as e:
#             raise CompletionRequestError(e.description)
#         except ValueError as e:
#             raise e
#         except Exception as e:
#             logging.exception("internal server error.")
#             raise InternalServerError()


# def compact_response(response: Union[dict, Generator]) -> Response:
#     if isinstance(response, dict):
#         return Response(response=json.dumps(response), status=200, mimetype='application/json')
#     else:
#         def generate() -> Generator:
#             yield from response

#         return Response(stream_with_context(generate()), status=200,
#                         mimetype='text/event-stream')


class ChatRobot(Resource):
    @dream_validate_cmd_token(
        fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True)
    )
    def post(self, app_model: App, end_user: EndUser):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        parser = reqparse.RequestParser()
        parser.add_argument("cmd", type=str, required=False, location="json")
        parser.add_argument("inputs", type=dict, required=True, location="json")
        parser.add_argument("query", type=str, required=True, location="json")
        parser.add_argument("files", type=list, required=False, location="json")
        parser.add_argument(
            "response_mode",
            type=str,
            choices=["blocking", "streaming"],
            location="json",
        )
        parser.add_argument("conversation_id", type=uuid_value, location="json")
        parser.add_argument(
            "retriever_from", type=str, required=False, default="dev", location="json"
        )
        parser.add_argument(
            "auto_generate_name",
            type=bool,
            required=False,
            default=True,
            location="json",
        )

        args = parser.parse_args()

        streaming = args["response_mode"] == "streaming"

        cmd = args["cmd"]
        if not cmd:
            marchs = QuestionService.march_app_question(
                app_model.tenant_id, args["query"]
            )
            marched_app_id = marchs.get("marched_app_id", None)
            if marched_app_id:
                marched_app_model = (
                    db.session.query(App).filter(App.id == marched_app_id).first()
                )
                if marched_app_model:
                    app_model = marched_app_model
        else:
            cmd_app_model = db.session.query(App).filter(App.cmd == cmd).first()
            if (
                cmd_app_model
                and cmd_app_model.status == "normal"
                and cmd_app_model.enable_api
            ):
                app_model = cmd_app_model
                if app_model.mode == AppMode.COMPLETION.value:
                    args["inputs"]["query"]=args["query"]

        try:
            response = AppGenerateService.generate(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.SERVICE_API,
                streaming=streaming,
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise e
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()


class ChatRobotStopApi(Resource):
    @dream_validate_cmd_token(
        fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True)
    )
    def post(self, app_model: App, end_user: EndUser, task_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        AppQueueManager.set_stop_flag(task_id, InvokeFrom.SERVICE_API, end_user.id)

        return {"result": "success"}, 200


api.add_resource(ChatRobot, "/chat_robot/")
api.add_resource(ChatRobotStopApi, "/chat_robot/<string:task_id>/stop")
