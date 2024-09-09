import uuid
from flask import Response, request
from flask_login import current_user
from flask_restful import Resource, marshal_with, reqparse
from flask_restful.inputs import url
from controllers.console.setup import setup_required
from fields.file_fields import file_fields
from libs.login import kaas_login_required
import services
from controllers.kaas_api import api
from controllers.service_api.app.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.kaas_api.wraps import validate_dream_ai_token
from fields.file_fields import chunck_attach_fields
import services.errors
import services.errors.file
from services.file_info_service import FileInfoService
from services.file_service import FileService




class ChunkAttachFileDownloadApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    def get(self, file_id):
        file_id = str(file_id)

        try:
            generator, mimetype = FileInfoService.download(
                file_id,
            )
            FileInfoService.attach_file_used(file_uuid=file_id)
        except Exception as e:
            raise e

        return Response(generator, mimetype=mimetype)


class ChunckFileApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    @validate_dream_ai_token(funcs={'and':['kaas:public']})
    @marshal_with(file_fields)
    def post(self):
        # tenant_id = str(current_user.current_tenant_id)

        # parser = reqparse.RequestParser()
        # parser.add_argument(
        #     "user", type=str, required=True, default=None, location="form"
        # )
        # parser.add_argument(
        #     "user_id", type=str, required=False, default=None, location="form"
        # )
        # args = parser.parse_args()
        # user = args["user"]
        # userId = args["user_id"]
        # end_user = (
        #     db.session.query(EndUser)
        #     .filter(
        #         EndUser.tenant_id == tenant_id,
        #         EndUser.session_id == user,
        #         EndUser.type == "service_api",
        #     )
        #     .first()
        # )

        # if end_user is None:
        #     end_user = EndUser(
        #         tenant_id=tenant_id,
        #         type="service_api",
        #         is_anonymous=False,
        #         name=user,
        #         external_user_id=userId,
        #         session_id=user,
        #     )
        #     db.session.add(end_user)
        #     db.session.commit()
        file = request.files["file"]

        # check file
        if "file" not in request.files:
            raise NoFileUploadedError()

        if not file.mimetype:
            raise UnsupportedFileTypeError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        try:
            upload_file = FileService.upload_file(file, current_user)
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()
        return upload_file, 201
    

class ChunkAttachFileInfosApi(Resource):

    # @validate_dataset_token()
    @setup_required
    @kaas_login_required
    def get(self, doc_seg_id: str):
        """
        通过文档段落ID获取附件信息。

        参数:
        doc_seg_id: str - 文档段落的唯一标识符。

        返回:
        返回调用FileService.get_chunck_attach_files_info方法的结果，该方法用于获取指定文档段落ID的附件信息。
        """

        return FileInfoService.get_chunck_attach_files_info(doc_seg_id)
    

class ChunkAttachFileApi(Resource):
    @setup_required
    @kaas_login_required
    def delete(self,  doc_seg_id: str):
        """
        通过文档段落ID和附件ID删除附件。

        参数:
        doc_seg_id: str - 文档段落的唯一标识符。
        file_id: str - 附件的唯一标识符。

        返回:
        返回调用FileService.delete_file_by_id方法的结果，该方法用于删除指定附件ID的附件。
        """
        parser = reqparse.RequestParser()
        parser.add_argument(
            "file_id", type=str, required=False, default=None, location="json"
        )
        args = parser.parse_args()
        return FileInfoService.delete_attach_file_by_id(doc_seg_id=doc_seg_id,file_id=args["file_id"])

    # @validate_dataset_token()#fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM)

    @setup_required
    @kaas_login_required
    @marshal_with(chunck_attach_fields)
    def post(self, doc_seg_id: uuid):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "file_id", type=str, required=False, default=None, location="json"
        )
        parser.add_argument(
            "url", type=url, required=False, default=None, location="json"
        )
        parser.add_argument(
            "user", type=str, required=False, default=None, location="json"
        )
        # parser.add_argument('doc_seg_id', type=uuid_value, required=True, location='json')
        parser.add_argument("isCover", type=bool, required=True, location="json")
        args = parser.parse_args()
        # check file
        if args["user"] is None:
            return {"msg": "user is required"}, 400
        try:

            docSegAttachFile = FileInfoService.bind_attach_to_chunck(
                args["file_id"], args["url"], args["user"], doc_seg_id, args["isCover"]
            )
        except Exception as e:
            raise e

        return docSegAttachFile, 200

    # @validate_dataset_token()#fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM)
    # @marshal_with(chunck_attach_fields)
    # def post(self, tenant_id,doc_seg_id:str):

    #     file = request.files['file']
    #     parser = reqparse.RequestParser()
    #     parser.add_argument('url', type=url,required=False,default=None, location='json')
    #     # parser.add_argument('doc_seg_id', type=uuid_value, required=True, location='json')
    #     parser.add_argument('isCover', type=bool, required=True, location='json')
    #     args = parser.parse_args()
    #     # check file
    #     if 'file' not in request.files:
    #         raise NoFileUploadedError()

    #     if not file.mimetype:
    #         raise UnsupportedFileTypeError()

    #     if len(request.files) > 1:
    #         raise TooManyFilesError()

    #     try:
    #         docSegAttachFile = FileService.upload_chunck_attach(file,args['url'],args['user'],doc_seg_id,args['isCover'])
    #     except services.errors.file.FileTooLargeError as file_too_large_error:
    #         raise FileTooLargeError(file_too_large_error.description)
    #     except services.errors.file.UnsupportedFileTypeError:
    #         raise UnsupportedFileTypeError()

    #     return docSegAttachFile, 201

class ChunkAttachFileInfoApi(Resource):
    @setup_required
    @kaas_login_required
    @marshal_with(file_fields)
    def get(self, file_ids: str):
        files = FileInfoService.get_file_info(file_ids)
        return [
            {
                "id": file.id,
                "name": file.name,
                "size": file.size,
                "extension": file.extension,
                "mime_type": file.mime_type,
                "created_by": file.created_by,
                "created_at": file.created_at,
            }
            for file in files
        ]
# 上传文件
api.add_resource(ChunckFileApi, "/attach/files/upload")
# 下载附件
api.add_resource(
    ChunkAttachFileDownloadApi, "/attach/files/<uuid:file_id>/download"
)
# 获取分段附件
api.add_resource(ChunkAttachFileInfosApi, "/attach/files/<uuid:doc_seg_id>/infos")
# 绑定附件，delete，删除附件
api.add_resource(ChunkAttachFileApi, "/attach/files/<uuid:doc_seg_id>/bind")
# 获取附件详情信息
api.add_resource(ChunkAttachFileInfoApi, "/attach/files/info/<file_ids>")