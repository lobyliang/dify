from flask import current_app
from flask_restful import Resource

from controllers.kaas_api import api


class IndexApi(Resource):
    def get(self):
        return {
            "welcome": "KaaS OpenAPI",
            "api_version": "v1",
            "server_version": current_app.config['CURRENT_VERSION']
        }


api.add_resource(IndexApi, '/')
