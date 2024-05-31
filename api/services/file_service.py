import datetime
import hashlib
from mimetypes import MimeTypes
from turtle import up
import uuid
from collections.abc import Generator
from typing import Union
import logging
from flask import current_app
from flask_login import current_user
from h11 import Response
import requests
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from core.file.upload_file_parser import UploadFileParser
from core.rag.extractor.extract_processor import ExtractProcessor
from extensions.ext_database import db
from extensions.ext_storage import storage
from models.account import Account
from models.dataset import DocumentSegment, DocumentSegmentsAttach
from models.model import EndUser, UploadFile
from services.errors.file import FileTooLargeError, UnsupportedFileTypeError

IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'svg']
IMAGE_EXTENSIONS.extend([ext.upper() for ext in IMAGE_EXTENSIONS])

ALLOWED_EXTENSIONS = ['txt', 'markdown', 'md', 'pdf', 'html', 'htm', 'xlsx', 'xls', 'docx', 'csv']
UNSTRUSTURED_ALLOWED_EXTENSIONS = ['txt', 'markdown', 'md', 'pdf', 'html', 'htm', 'xlsx', 'xls',
                                   'docx', 'csv', 'eml', 'msg', 'pptx', 'ppt', 'xml', 'epub']

PREVIEW_WORDS_LIMIT = 3000


class FileService:
    @staticmethod
    def get_url_file_info(url):
        try:
            response = requests.head(url)
            content_length = response.headers.get('Content-Length')
            content_disposition = response.headers.get('Content-Disposition')
            content_type = response.headers.get('Content-Type')
            extention = ''
            # 解析Content-Disposition获取文件名（如果存在）
            file_name = None
            if content_disposition:
                dispositions = dict(item.split('=') for item in content_disposition.split(';'))
                if 'filename' in dispositions:
                    file_name = dispositions['filename'].strip('"\'')
                    if file_name:
                        extention = file_name.split('.')[-1]
            else:
                file_name = url.split('/')[-1]
                extention = file_name.split('.')[-1]

            if not content_type:
                mime = MimeTypes()
                content_type = mime.guess_type(file_name)[0]
                if content_type and ';' in content_type:
                    content_type = content_type.split(';')[0]

            return {
                'file_size': int(content_length) if content_length else 0,
                'file_name': file_name,
                'extention': extention,
                'mime_type':content_type,
            }
        except requests.exceptions.RequestException as e:
            print(f"Error fetching URL: {e}")
            return None, None
        
    @staticmethod
    def download(file_id: str) -> tuple[Generator, str]:

        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        generator = storage.load(upload_file.key, stream=True)

        return generator, upload_file.mime_type

    #上传文件，并绑定到知识库的分片上
    @staticmethod
    def upload_chunck_attach(file: FileStorage,url:str,user: str, doc_seg_id:uuid,isCover:bool = False) -> DocumentSegmentsAttach:
        file_uuid = str(uuid.uuid4())
        doc_seg = db.session.query(DocumentSegment) \
            .filter(DocumentSegment.id == doc_seg_id) \
            .first()
        if not doc_seg:
            raise NotFound("DocumentSegment not found")

        dataset_id = doc_seg.dataset_id

        if file:
            file_name = file.filename
            extension = file_name.split('.')[-1]
            mime_type = file.mimetype
            # read file content
            file_content = file.read()

            # get file size
            file_size = len(file_content)

            if extension.lower() in IMAGE_EXTENSIONS:
                file_size_limit = current_app.config.get("UPLOAD_IMAGE_FILE_SIZE_LIMIT") * 1024 * 1024
            else:
                file_size_limit = current_app.config.get("UPLOAD_FILE_SIZE_LIMIT") * 1024 * 1024

            if file_size > file_size_limit:
                message = f'File size exceeded. {file_size} > {file_size_limit}'
                raise FileTooLargeError(message)
            file_key = 'upload_files/chunk_attachs/' + dataset_id +'/'+doc_seg_id+ '/' + file_uuid + '.' + extension
            storage.save(file_key, file_content)
            source = 'file'
        elif url:
            info = FileService.get_url_file_info(url)
            extension = info['extention']
            file_size = info['file_size']
            file_name = info['file_name']
            mime_type = info['mime_type']
            source = 'url'
            file_key = url

        config = current_app.config
        doc_seg_attch = DocumentSegmentsAttach(
            id=file_uuid,
            doc_seg_id=doc_seg_id,
            attach_type = 'cover' if isCover else 'attach',
            source= source,
            storage_type=config['STORAGE_TYPE'],
            file_name = file_name,
            size=file_size,
            file = file_key,
            mime_type = mime_type,
            extension=extension,
            created_by=user
        )
        db.session.add(doc_seg_attch)
        db.session.commit()

        return doc_seg_attch
    
    # def download(file_uuid:uuid):
    #     storage.download()

    @staticmethod
    def delete_attach_file_by_id(file_id:str):
        try:
            doc_seg_attch = db.session.query(DocumentSegmentsAttach) \
                .filter(DocumentSegmentsAttach.file == file_id).first()
            if doc_seg_attch:
                db.session.delete(doc_seg_attch) 
            uploadFile = db.session.query(UploadFile).filter(UploadFile.id == file_id)
            if uploadFile:
                db.session.delete(uploadFile)
            if doc_seg_attch.source == 'file':
                storage.delete(doc_seg_attch.file)
            # db.session.delete(doc_seg_attch)
        except Exception as e:
            logging.info("删除文件失败",e)
            return Response(status=400,msg="删除文件失败")
        db.session.commit()

        return Response(status=200,msg="删除文件成功")
    
    @staticmethod
    def attach_file_used(file_uuid:uuid):
        doc_seg_attch = db.session.query(DocumentSegmentsAttach) \
            .filter(DocumentSegmentsAttach.file == str(file_uuid)).first()
        
        if doc_seg_attch:
            doc_seg_attch.used_times += 1
            db.session.commit()
    #上传文件，并绑定到知识库的分片上
    @staticmethod
    def bind_attach_to_chunck(file_uuid:uuid,url:str,user: str, doc_seg_id:uuid,isCover:bool = False) -> DocumentSegmentsAttach:
        doc_seg = db.session.query(DocumentSegment) \
            .filter(DocumentSegment.id == str(doc_seg_id)) \
            .first()
        if not doc_seg:
            raise NotFound("DocumentSegment not found")

        dataset_id = doc_seg.dataset_id

        if file_uuid:
            source = 'file'
            file_key = str(file_uuid)
            upload_file = db.session.query(UploadFile).filter(UploadFile.id == file_uuid).first()
            extension = upload_file.extension
            file_size = upload_file.size
            file_name = upload_file.name
            mime_type = upload_file.mime_type
            storage_type= upload_file.storage_type

        elif url:
            info = FileService.get_url_file_info(url)
            storage_type = 'URL'
            extension = info['extention']
            file_size = info['file_size']
            file_name = info['file_name']
            mime_type = info['mime_type']
            source = 'url'
            file_key = url

        doc_seg_attch = DocumentSegmentsAttach(
            # id=file_uuid,
            doc_seg_id=doc_seg_id,
            attach_type = 'cover' if isCover else 'attach',
            source= source,
            storage_type=storage_type,
            file_name = file_name,
            size=file_size,
            file = file_key,
            mime_type = mime_type,
            extension=extension,
            created_by=user
        )
        db.session.add(doc_seg_attch)
        db.session.commit()

        return doc_seg_attch
    @staticmethod
    def get_chunck_attach_files_info(doc_seg_id:str):
        doc_seg_attch = db.session.query(DocumentSegmentsAttach)\
            .filter(DocumentSegmentsAttach.doc_seg_id == doc_seg_id) \
            .all()
        if not doc_seg_attch:
            return {}
        
        ret = {'cover':[],'attach':[]}

        for doc_seg_attch in doc_seg_attch:
            if doc_seg_attch.attach_type == 'cover':
                ret['cover'].append({
                    'id':doc_seg_attch.id,
                    'source':doc_seg_attch.source,
                    'file_name':doc_seg_attch.file_name,
                    'size':doc_seg_attch.size,
                    'mime_type':doc_seg_attch.mime_type,
                    'extension':doc_seg_attch.extension,
                    'file':doc_seg_attch.file,
                    'created_by':doc_seg_attch.created_by,
                    'created_at':str(doc_seg_attch.created_at),})
            else:
                ret['attach'].append({
                    'id':doc_seg_attch.id,
                    'source':doc_seg_attch.source,
                    'file_name':doc_seg_attch.file_name,
                    'size':doc_seg_attch.size,
                    'mime_type':doc_seg_attch.mime_type,
                    'extension':doc_seg_attch.extension,
                    'file':doc_seg_attch.file,
                    'created_by':doc_seg_attch.created_by,
                    'created_at':str(doc_seg_attch.created_at),})
        
        return ret
    
    # @staticmethod
    # def get_chunck_attach_files_info(doc_seg_id:str):
    #     doc_seg_attch = db.session.query(DocumentSegmentsAttach) \
    #         .filter(DocumentSegmentsAttach.doc_seg_id == doc_seg_id) \
    #         .all()
    #     if not doc_seg_attch:
    #         return {}
        
    #     ret = {'cover':[],'attach':[]}



    #     for doc_seg_attch in doc_seg_attch:
    #         if doc_seg_attch.attach_type == 'cover':
    #             ret['cover'].append({
    #                 'id':doc_seg_attch.id,
    #                 'source':doc_seg_attch.source,
    #                 'file_name':doc_seg_attch.file_name,
    #                 'size':doc_seg_attch.size,
    #                 'mime_type':doc_seg_attch.mime_type,
    #                 'extension':doc_seg_attch.extension,
    #                 'file':doc_seg_attch.file,
    #                 'created_by':doc_seg_attch.created_by,
    #                 'created_at':doc_seg_attch.created_at,})
    #         else:
    #             ret['attach'].append({
    #                 'id':doc_seg_attch.id,
    #                 'source':doc_seg_attch.source,
    #                 'file_name':doc_seg_attch.file_name,
    #                 'size':doc_seg_attch.size,
    #                 'mime_type':doc_seg_attch.mime_type,
    #                 'extension':doc_seg_attch.extension,
    #                 'file':doc_seg_attch.file,
    #                 'created_by':doc_seg_attch.created_by,
    #                 'created_at':doc_seg_attch.created_at,})
        
    #     return ret

    @staticmethod
    def upload_file(file: FileStorage, user: Union[Account, EndUser], only_image: bool = False) -> UploadFile:
        extension = file.filename.split('.')[-1]
        etl_type = current_app.config['ETL_TYPE']
        allowed_extensions = UNSTRUSTURED_ALLOWED_EXTENSIONS + IMAGE_EXTENSIONS if etl_type == 'Unstructured' \
            else ALLOWED_EXTENSIONS + IMAGE_EXTENSIONS
        if extension.lower() not in allowed_extensions:
            raise UnsupportedFileTypeError()
        elif only_image and extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        # read file content
        file_content = file.read()

        # get file size
        file_size = len(file_content)

        if extension.lower() in IMAGE_EXTENSIONS:
            file_size_limit = current_app.config.get("UPLOAD_IMAGE_FILE_SIZE_LIMIT") * 1024 * 1024
        else:
            file_size_limit = current_app.config.get("UPLOAD_FILE_SIZE_LIMIT") * 1024 * 1024

        if file_size > file_size_limit:
            message = f'File size exceeded. {file_size} > {file_size_limit}'
            raise FileTooLargeError(message)

        # user uuid as file name
        file_uuid = str(uuid.uuid4())

        if isinstance(user, Account):
            current_tenant_id = user.current_tenant_id
        else:
            # end_user
            current_tenant_id = user.tenant_id

        file_key = 'upload_files/' + current_tenant_id + '/' + file_uuid + '.' + extension

        # save file to storage
        storage.save(file_key, file_content)

        # save file to db
        config = current_app.config
        upload_file = UploadFile(
            tenant_id=current_tenant_id,
            storage_type=config['STORAGE_TYPE'],
            key=file_key,
            name=file.filename,
            size=file_size,
            extension=extension,
            mime_type=file.mimetype,
            created_by_role=('account' if isinstance(user, Account) else 'end_user'),
            created_by=user.id,
            created_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            used=False,
            hash=hashlib.sha3_256(file_content).hexdigest()
        )

        db.session.add(upload_file)
        db.session.commit()

        return upload_file

    @staticmethod
    def upload_text(text: str, text_name: str) -> UploadFile:
        # user uuid as file name
        file_uuid = str(uuid.uuid4())
        file_key = 'upload_files/' + current_user.current_tenant_id + '/' + file_uuid + '.txt'

        # save file to storage
        storage.save(file_key, text.encode('utf-8'))

        # save file to db
        config = current_app.config
        upload_file = UploadFile(
            tenant_id=current_user.current_tenant_id,
            storage_type=config['STORAGE_TYPE'],
            key=file_key,
            name=text_name + '.txt',
            size=len(text),
            extension='txt',
            mime_type='text/plain',
            created_by=current_user.id,
            created_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            used=True,
            used_by=current_user.id,
            used_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        )

        db.session.add(upload_file)
        db.session.commit()

        return upload_file

    @staticmethod
    def get_file_preview(file_id: str) -> str:
        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found")

        # extract text from file
        extension = upload_file.extension
        etl_type = current_app.config['ETL_TYPE']
        allowed_extensions = UNSTRUSTURED_ALLOWED_EXTENSIONS if etl_type == 'Unstructured' else ALLOWED_EXTENSIONS
        if extension.lower() not in allowed_extensions:
            raise UnsupportedFileTypeError()

        text = ExtractProcessor.load_from_upload_file(upload_file, return_text=True)
        text = text[0:PREVIEW_WORDS_LIMIT] if text else ''

        return text

    @staticmethod
    def get_image_preview(file_id: str, timestamp: str, nonce: str, sign: str) -> tuple[Generator, str]:
        result = UploadFileParser.verify_image_file_signature(file_id, timestamp, nonce, sign)
        if not result:
            raise NotFound("File not found or signature is invalid")

        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        generator = storage.load(upload_file.key, stream=True)

        return generator, upload_file.mime_type

    @staticmethod
    def get_public_image_preview(file_id: str) -> tuple[Generator, str]:
        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # extract text from file
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        generator = storage.load(upload_file.key)

        return generator, upload_file.mime_type
