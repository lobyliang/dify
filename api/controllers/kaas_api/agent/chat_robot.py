import logging
from flask_restful import Resource, reqparse
from controllers.console.setup import setup_required
from controllers.service_api.app.error import AppUnavailableError, CompletionRequestError, ConversationCompletedError, NotChatAppError, ProviderModelCurrentlyNotSupportError, ProviderNotInitializeError, ProviderQuotaExceededError
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
import services
from services.app_generate_service import AppGenerateService
from libs import helper
from libs.helper import uuid_value
from extensions.ext_database import db
from models.model import App, AppMode
from controllers.kaas_api import api
from libs.login import current_user, kaas_login_required
from werkzeug.exceptions import NotFound,InternalServerError

from services.dc_question_service import QuestionService
import services.errors
import services.errors.app_model_config
import services.errors.conversation

class AgentChatRobot(Resource):
    # @dream_validate_cmd_token(
    #     fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True)
    # )
    @setup_required
    @kaas_login_required
    def post(self, app_model: App):
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
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.KAAS_API,
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


class AgentChatRobotStopApi(Resource):
    # @dream_validate_cmd_token(
    #     fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True)
    # )
    @setup_required
    @kaas_login_required
    def post(self, app_model: App, task_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        AppQueueManager.set_stop_flag(task_id, InvokeFrom.KAAS_API, current_user.id)

        return {"result": "success"}, 200


api.add_resource(AgentChatRobot, "/agent/chat_robot/")
api.add_resource(AgentChatRobotStopApi, "/agent/chat_robot/<string:task_id>/stop")
