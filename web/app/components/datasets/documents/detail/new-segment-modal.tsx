import { memo, useState } from "react";
import type { FC } from "react";
import { useTranslation } from "react-i18next";
import { useContext } from "use-context-selector";
import { useParams } from "next/navigation";
import Modal from "@/app/components/base/modal";
import Button from "@/app/components/base/button";
import AutoHeightTextarea from "@/app/components/base/auto-height-textarea/common";
import {
  Hash02,
  XClose,
} from "@/app/components/base/icons/src/vender/line/general";
import { ToastContext } from "@/app/components/base/toast";
import FileUpload from "@/app/components/base/file-upload";
import type { SegmentUpdator } from "@/models/datasets";
import { addSegment } from "@/service/datasets";
import TagInput from "@/app/components/base/tag-input";
import { bindSegFile } from "@/service/v1/chunckAttach/files";

type NewSegmentModalProps = {
  isShow: boolean;
  onCancel: () => void;
  docForm: string;
  onSave: () => void;
};

const NewSegmentModal: FC<NewSegmentModalProps> = ({
  isShow,
  onCancel,
  docForm,
  onSave,
}) => {
  const { t } = useTranslation();
  const { notify } = useContext(ToastContext);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [fileCover, setFileCover] = useState("");
  const { datasetId, documentId } = useParams() as {
    datasetId: string;
    documentId: string;
  };
  const [keywords, setKeywords] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const handleCancel = () => {
    setQuestion("");
    setAnswer("");
    onCancel();
    setKeywords([]);
    setFileUrl("");
    setFileCover("");
  };

  const handleSave = async () => {
    const params: SegmentUpdator = { content: "" };
    if (docForm === "qa_model") {
      if (!question.trim())
        return notify({
          type: "error",
          message: t("datasetDocuments.segment.questionEmpty"),
        });
      if (!answer.trim())
        return notify({
          type: "error",
          message: t("datasetDocuments.segment.answerEmpty"),
        });

      params.content = question;
      params.answer = answer;
    } else {
      if (!question.trim())
        return notify({
          type: "error",
          message: t("datasetDocuments.segment.contentEmpty"),
        });

      params.content = question;
    }

    if (keywords?.length) params.keywords = keywords;

    setLoading(true);
    try {
      const { data } = await addSegment({
        datasetId,
        documentId,
        body: params,
      });

      const segmentId = data.id;
      if (fileUrl?.split(",").filter((item) => item).length > 0)
        Promise.all(
          fileUrl.split(",").map((url) =>
            bindSegFile(segmentId, {
              file_id: url,
              isCover: false,
              user: "测试用户",
            }),
          ),
        );
      if (fileCover?.split(",").filter((item) => item).length > 0)
        Promise.all(
          fileCover.split(",").map((url) =>
            bindSegFile(segmentId, {
              file_id: url,
              isCover: true,
              user: "测试用户",
            }),
          ),
        );
      notify({
        type: "success",
        message: t("common.actionMsg.modifiedSuccessfully"),
      });
      handleCancel();
      onSave();
    } finally {
      setLoading(false);
    }
  };

  const onRemoveFile = (file: any) => {};

  const renderContent = () => {
    if (docForm === "qa_model") {
      return (
        <>
          <div className="mb-1 text-xs font-medium text-gray-500">问题</div>
          <AutoHeightTextarea
            outerClassName="mb-4"
            className="leading-6 text-md text-gray-800"
            value={question}
            placeholder={
              t("datasetDocuments.segment.questionPlaceholder") || ""
            }
            onChange={(e) => setQuestion(e.target.value)}
            autoFocus
          />
          <div className="mb-1 text-xs font-medium text-gray-500">答案</div>
          <AutoHeightTextarea
            outerClassName="mb-4"
            className="leading-6 text-md text-gray-800"
            value={answer}
            placeholder={t("datasetDocuments.segment.answerPlaceholder") || ""}
            onChange={(e) => setAnswer(e.target.value)}
          />
        </>
      );
    }

    return (
      <AutoHeightTextarea
        className="leading-6 text-md text-gray-800"
        value={question}
        placeholder={t("datasetDocuments.segment.contentPlaceholder") || ""}
        onChange={(e) => setQuestion(e.target.value)}
        autoFocus
      />
    );
  };

  const renderFileCover = () => {
    return (
      <>
        <div className="text-xs font-medium text-gray-500">封面</div>
        <div>
          <FileUpload
            fileUrl={fileCover}
            onChange={(file: string) => {
              setFileCover(file);
            }}
            onRemove={onRemoveFile}
          ></FileUpload>
        </div>
      </>
    );
  };

  const renderFileContent = () => {
    return (
      <>
        <div className="text-xs font-medium text-gray-500">附件</div>
        <div>
          <FileUpload
            fileUrl={fileUrl}
            onChange={(file: string) => {
              setFileUrl(file);
            }}
            onRemove={onRemoveFile}
          ></FileUpload>
        </div>
      </>
    );
  };

  return (
    <Modal
      isShow={isShow}
      onClose={() => {}}
      className="pt-8 px-8 pb-6 !max-w-[640px] !rounded-xl"
    >
      <div className={"flex flex-col relative"}>
        <div className="absolute right-0 -top-0.5 flex items-center h-6">
          <div
            className="flex justify-center items-center w-6 h-6 cursor-pointer"
            onClick={handleCancel}
          >
            <XClose className="w-4 h-4 text-gray-500" />
          </div>
        </div>
        <div className="mb-[14px]">
          <span className="inline-flex items-center px-1.5 h-5 border border-gray-200 rounded-md">
            <Hash02 className="mr-0.5 w-3 h-3 text-gray-400" />
            <span className="text-[11px] font-medium text-gray-500 italic">
              {docForm === "qa_model"
                ? t("datasetDocuments.segment.newQaSegment")
                : t("datasetDocuments.segment.newTextSegment")}
            </span>
          </span>
        </div>
        <div className="mb-4 py-1.5 h-[420px] overflow-auto">
          {renderContent()}
        </div>
        <div className="mb-2">{renderFileCover()}</div>
        <div className="mb-2">{renderFileContent()}</div>
        <div className="text-xs font-medium text-gray-500">
          {t("datasetDocuments.segment.keywords")}
        </div>
        <div className="mb-8">
          <TagInput
            items={keywords}
            onChange={(newKeywords) => setKeywords(newKeywords)}
          />
        </div>
        <div className="flex justify-end">
          <Button
            className="mr-2 !h-9 !px-4 !py-2 text-sm font-medium text-gray-700 !rounded-lg"
            onClick={handleCancel}
          >
            {t("common.operation.cancel")}
          </Button>
          <Button
            type="primary"
            className="!h-9 !px-4 !py-2 text-sm font-medium !rounded-lg"
            onClick={handleSave}
            disabled={loading}
          >
            {t("common.operation.save")}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default memo(NewSegmentModal);
