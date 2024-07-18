from jinja2 import Template
import logging
import json
from flask_restful import reqparse
from core.helper.code_executor.jinja2 import jinja2_formatter
from controllers.service_api import api
from controllers.service_api.wraps import DatasetApiResource


class JinJaTransformApi(DatasetApiResource):
    def post(self, tenant_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("templateStr", type=str, required=True)
            parser.add_argument("jsonStr", type=dict, required=True)
            # parser.add_argument('jsonDict', type=dict, required=True)
            args = parser.parse_args()
            templateStr = args.get("templateStr")
            templateStr = templateStr.replace("%1", "{%")
            templateStr = templateStr.replace("%2", "%}")
            jsonStr = args.get("jsonStr")
            jsonDict = args.get("jsonDict")
            if jsonStr == None and jsonDict == None:
                raise Exception("jsonStr and jsonDict can not be both None")
            template = Template(templateStr)
            jsonObj = None
            if jsonStr != None:
                try:
                    jsonObj = jsonStr  # json.loads(jsonStr)
                except Exception as e:
                    raise Exception("template is not valid")
            else:
                jsonObj = jsonDict
            # args = {"WorkExperience":jsonObj["WorkExperience"]}
            ret = jinja2_formatter.Jinja2Formatter.format(
                templateStr, json.dumps(jsonObj)
            )
            result = template.render(args)
            return {"result": result}, 200
        except Exception as e:
            logging.error(e)
            return {"message": str(e)}, 500


api.add_resource(JinJaTransformApi, "/jinja2/transform")
