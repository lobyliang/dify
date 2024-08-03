import logging

from flask import request
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError

from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, dream_validate_cmd_token
from models.model import App, EndUser
import services
from controllers.console import api
from controllers.console.app import _get_app_without_user
from controllers.console.app.error import (
    AppUnavailableError,
    AudioTooLargeError,
    CompletionRequestError,
    NoAudioUploadedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderNotSupportSpeechToTextError,
    ProviderQuotaExceededError,
    UnsupportedAudioTypeError,
)

# from controllers.console.wraps import dream_ai_token_required
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError

from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)

import base64
import io
from extensions.ext_database import db
# from pydub import AudioSegment
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

class ChatMessageBase64AudioApi(Resource):
    # def _get_app_without_user(app_id, mode=None):
    #     app = db.session.query(App).filter(
    #         App.id == app_id,
    #         # App.tenant_id == current_user.current_tenant_id,
    #         App.status == 'normal'
    #     ).first()

    #     if not app:
    #         raise NotFound("App not found")

    #     if mode and app.mode != mode:
    #         raise NotFound("The {} app not found".format(mode))

    #     return app
    

    # @dream_ai_token_required
    @dream_validate_cmd_token(
        fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True)
    )
    def post(self,app_model: App, end_user: EndUser):
        # app_id = 'dff6330d-dbe8-4473-a092-0e1be534413d'# str(app_id)
        # app_model = self._get_app_without_user(app_id, 'chat') 

        file = request.json['file']#.json
        audio_bytes = base64.b64decode(file)
        audio_file = io.BytesIO(audio_bytes)
        
        file = FileStorage(content_type="audio/mp3",stream=audio_file,name="audioFile",content_length=audio_bytes.count)
        
        try:
            response = AudioService.transcript_asr(
                app_model=app_model,
                file=file,
                end_user=end_user,
            )

            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            raise ProviderNotSupportSpeechToTextError()
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
            logging.exception(f"internal server error, {str(e)}.")
            raise InternalServerError()

api.add_resource(ChatMessageBase64AudioApi, '/audio/audio-to-text')

