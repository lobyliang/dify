from flask import Blueprint

from libs.external_api import ExternalApi

bp = Blueprint('service_api', __name__, url_prefix='/v1')
api = ExternalApi(bp)


from . import index
from .app import app, audio, completion, conversation, file, message, workflow,dc_app
from .dataset import dataset, document, segment
from .dc_auth import tenant,wechat_login
from .dc_dataset import chunckattach,ds_create,ds_query,hit_testing,ds_app
from .robot import app_questions,key_word_march,jinja2_transformer,chat_robot,dc_audio
from .wechat_app import dc_wechat_account_app