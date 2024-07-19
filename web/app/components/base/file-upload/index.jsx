import React, { useEffect, useReducer, useState } from "react";
import {
  LoadingOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Upload, message, Button } from "antd";
import { filesUpload, fetchFilesList } from "@/service/v1/chunckAttach/files";

const getBase64 = (img, callback) => {
  const reader = new FileReader();
  reader.addEventListener("load", () => callback(reader.result));
  reader.readAsDataURL(img);
};
const beforeUpload = (file) => {
  // const isJpgOrPng = file.type === "image/jpeg" || file.type === "image/png";
  // if (!isJpgOrPng) message.error("You can only upload JPG/PNG file!");

  const isLt2M = file.size / 1024 / 1024 < 2;
  if (!isLt2M) message.error("Image must smaller than 2MB!");

  // return isJpgOrPng && isLt2M;
  return isLt2M;
};

const FileUpload = ({ fileUrl, onChange, disabled = false, onRemove }) => {
  const [fileList, setFileList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [imageUrl, setImageUrl] = useState();

  const handleChange = (info) => {
    info.fileList.forEach((item) => {
      if (item.response?.id) {
        item.url = item.response?.id;
      }
    });
    setFileList(info.fileList);
    if (info.file.status === "uploading") {
      setLoading(true);
      return;
    }
    if (info.file.status === "done") {
      onChange(info.fileList.map((item) => item.url).join(","));
      getBase64(info.file.originFileObj, (url) => {
        setLoading(false);
        setImageUrl(url);
      });
    }
  };

  const handleRemove = (file) => {
    const list = fileList.filter((item) => item.uid !== file.uid);
    setFileList(list);
    onChange(list.join(","));
    onRemove(file);
  };

  const uploadButton = (
    // <button
    //   style={{
    //     border: 0,
    //     background: "none",
    //   }}
    //   type="button"
    // >
    //   {loading ? <LoadingOutlined /> : <PlusOutlined />}
    //   <div
    //     style={{
    //       marginTop: 8,
    //     }}
    //   >
    //     上传
    //   </div>
    // </button>
    <Button icon={<UploadOutlined />}>上传</Button>
  );

  const customRequest = (option) => {
    const { onSuccess, onError, file } = option;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("user", "测试用户");
    filesUpload(formData)
      .then((res) => {
        onSuccess(res);
      })
      .catch((err) => {
        onError(err);
      });
  };

  useEffect(() => {
    (async () => {
      if (fileUrl) {
        // 首先将值转为数组
        let list = [];
        if (Array.isArray(fileUrl)) {
          list = fileUrl;
        } else {
          const data = await fetchFilesList(fileUrl);
          list = data;
        }
        setFileList(
          list.map((item) => {
            let itemData;
            if (typeof item === "string") {
              itemData = {
                name: item,
                url: item,
                status: "done",
                uid: item,
              };
            } else {
              // 此处name使用ossId 防止删除出现重名
              itemData = {
                name: item.name,
                url: item.id,
                status: "done",
                uid: item.id,
              };
            }
            return itemData;
          }),
        );
      } else {
        setFileList([]);
      }
    })();
  }, [fileUrl]);
  return (
    <>
      <Upload
        name="file"
        className="avatar-uploader"
        beforeUpload={beforeUpload}
        onChange={handleChange}
        customRequest={customRequest}
        fileList={fileList}
        disabled={disabled}
        onRemove={handleRemove}
      >
        {!disabled ? uploadButton : ""}
      </Upload>
    </>
  );
};

export default FileUpload;
