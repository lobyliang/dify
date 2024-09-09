from flask import Blueprint

from libs.external_api import ExternalApi

bp = Blueprint('kaas_api', __name__, url_prefix='/kaas')
api = ExternalApi(bp)


from . import index
from .auth import role_manage
from .agent import agent_questions,agent
from .dataset import attach,search,document,hit_test,query_history,segment,dataset,batch_hit_test
