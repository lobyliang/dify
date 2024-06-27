import json
import logging
from collections.abc import Generator
from typing import Union

from flask import Response, stream_with_context
from flask_restful import Resource,reqparse
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
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_cmd_app_token
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs.helper import datetime_string
from services.chat_robot_service import ChatRebotService
from datetime import datetime

import services.errors
import services.errors.app_model_config
import services.errors.conversation

class TenantTokens(Resource):
    @validate_cmd_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def get(self,app_token:str):
        parser = reqparse.RequestParser()
        parser.add_argument('beginTime', type=datetime_string('%Y-%m-%d %H:%M'), required=False, location='json')
        parser.add_argument('endTime', type=datetime_string('%Y-%m-%d %H:%M'), required=False, location='json')

        args = parser.parse_args()

        if args['beginTime']:
            begTime = datetime.strptime(args['beginTime'], '%Y-%m-%d %H:%M')
            begTime = begTime.replace(second=0)
        else:
            begTime = datetime.min

        if args['endTime']:
            endTime = datetime.strptime(args['endTime'], '%Y-%m-%d %H:%M')
            endTime = endTime.replace(second=0)
        else:
            endTime = datetime.now()

        try:
            response = ChatRebotService.get_tenant_token_consume(app_token=app_token,begTime=begTime,endTime=endTime)

            return compact_response(response)
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


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')

api.add_resource(TenantTokens, '/chat_robot/tokens/')

