import json
import logging

from flask import Response
from flask_restful import Resource
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.service_api.wraps import dream_validate_app_token# validate_app_token

from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError

from services.chat_robot_service import ChatRebotService
import services.errors
import services.errors.app_model_config
import services.errors.conversation


class CmdCategories(Resource):
    # @validate_cmd_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=False))
    # @validate_app_token()
    @dream_validate_app_token()
    def get(self):
        
        try:
            cmds = ChatRebotService.get_cmds()

            return  Response(response=json.dumps(cmds), status=200, mimetype='application/json')
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

api.add_resource(CmdCategories, '/chat_robot/categories/')

