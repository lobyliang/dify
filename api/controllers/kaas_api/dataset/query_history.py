import logging
from flask_restful import Resource, reqparse
from core.rag.retrieval.dc_retrieval.custom_dataset_retrieval import CustomDataSetRetrieval
from controllers.console.setup import setup_required
from controllers.kaas_api import api
from libs.login import kaas_login_required




class RAGDocumentCommnetListApi(Resource):

    # @marshal_with(document_fields)
    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument(
                "page_no", type=int, required=True, nullable=False, location="args"
            )
            parser.add_argument(
                "page_size", type=int, required=True, nullable=False, location="args"
            )
            args = parser.parse_args()
            page_no = args["page_no"]
            page_size = args["page_size"]
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.document_comment_list_in_dataset(
                dataset_id, page_no=page_no, page_size=page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200
    

class RAGChunkCommnetListApi(Resource):

    # @marshal_with(document_fields)
    @setup_required
    @kaas_login_required
    def get(self, segment_id: str):

        try:
            parser = reqparse.RequestParser()
            parser.add_argument(
                "page_no", type=int, required=True, nullable=False, location="args"
            )
            parser.add_argument(
                "page_size", type=int, required=True, nullable=False, location="args"
            )
            args = parser.parse_args()
            page_no = args["page_no"]
            page_size = args["page_size"]
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.chunck_comment_list(
                str(segment_id), page_no=page_no, page_size=page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200
    

class RAGCommnetListApi(Resource):

    # @marshal_with(document_fields)
    @setup_required
    @kaas_login_required
    def get(self, dataset_id):
        # The role of the current user in the ta table must be admin or owner
        # if not current_user.is_admin_or_owner:
        #     raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument(
            "page_no", type=int, required=True, nullable=False, location="args"
        )
        parser.add_argument(
            "page_size", type=int, required=True, nullable=False, location="args"
        )
        args = parser.parse_args()
        page_no = args["page_no"]
        page_size = args["page_size"]
        try:
            custom_dataset_retrieval = CustomDataSetRetrieval()
            ret = custom_dataset_retrieval.dataset_comment_list(
                dataset_id, page_no, page_size
            )
        except Exception as e:
            logging.error(e)
            raise e
        return ret, 200
    
# 获取分段命中统计
api.add_resource(RAGDocumentCommnetListApi, "/statistics/datasets/<uuid:dataset_id>/documents/comments")
# 获取分段匹配查询记录
api.add_resource(RAGChunkCommnetListApi, "/statistics/datasets/chunck/<uuid:segment_id>")
# 获取命中统计
api.add_resource(RAGCommnetListApi, "/statistics/datasets/<uuid:dataset_id>/comments")