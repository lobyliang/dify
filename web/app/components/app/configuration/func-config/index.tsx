"use client";
import type { FC } from "react";
import React from "react";
import { useTranslation } from "react-i18next";
import { useContext } from "use-context-selector";
import produce from "immer";
import { useFormattingChangedDispatcher } from "../debug/hooks";
import FeaturePanel from "../base/feature-panel";
import ParamsConfig from "./params-config";
import ContextVar from "./context-var";
import InputItem from "./input-item";
import CardItem from "./card-item/item";
import style from "./style.module.css";
import ConfigContext from "@/context/debug-configuration";
import { AppType } from "@/types/app";
import IconImg from "@/app/components/app/configuration/func-config/icon-img";

const Icon = (
  <svg
    className="icon"
    viewBox="0 0 1024 1024"
    version="1.1"
    xmlns="http://www.w3.org/2000/svg"
    p-id="4443"
    width="16"
    height="16"
  >
    <path
      d="M512 81.92l372.736 215.04v430.08L512 942.08 139.264 727.04v-430.08L512 81.92m0-81.92c-14.336 0-28.672 4.096-40.96 10.24L98.304 225.28c-24.576 14.336-40.96 40.96-40.96 71.68v430.08c0 28.672 16.384 55.296 40.96 71.68L471.04 1013.76c12.288 8.192 26.624 10.24 40.96 10.24s28.672-4.096 40.96-10.24L925.696 798.72c24.576-14.336 40.96-40.96 40.96-71.68v-430.08c0-28.672-16.384-55.296-40.96-71.68L552.96 10.24c-12.288-6.144-26.624-10.24-40.96-10.24z"
      p-id="4444"
      fill="#1195db"
    ></path>
    <path
      d="M698.368 352.256L532.48 450.56c-12.288 8.192-28.672 8.192-43.008 0l-153.6-96.256c-18.432-12.288-45.056-6.144-57.344 12.288-12.288 18.432-6.144 45.056 12.288 57.344l157.696 98.304c12.288 8.192 18.432 20.48 18.432 34.816V757.76c0 22.528 18.432 40.96 40.96 40.96s40.96-18.432 40.96-40.96v-200.704c0-14.336 8.192-28.672 20.48-34.816l167.936-100.352c20.48-12.288 26.624-36.864 14.336-55.296-8.192-20.48-32.768-26.624-53.248-14.336z"
      p-id="4445"
      fill="#1195db"
    ></path>
  </svg>
);

const DatasetConfig: FC = () => {
  const { t } = useTranslation();
  const {
    mode,
    dataSets: dataSet,
    setting,
    setSetting,
    setDataSets: setDataSet,
    modelConfig,
    setModelConfig,
    showSelectDataSet,
    isAgent,
  } = useContext(ConfigContext);
  const formattingChangedDispatcher = useFormattingChangedDispatcher();

  const hasData = dataSet.length > 0;

  const onRemove = (index: number) => {
    // setting.matchList = setting.matchList.filter((item, i) => i !== index)
    setSetting({
      ...setting,
      match_list: setting.match_list.filter((item, i) => i !== index),
    });
    formattingChangedDispatcher();
  };

  const promptVariables = modelConfig.configs.prompt_variables;
  const promptVariablesToSelect = promptVariables.map((item) => ({
    name: item.name,
    type: item.type,
    value: item.key,
  }));
  const selectedContextVar = promptVariables?.find(
    (item) => item.is_context_var,
  );
  const handleSelectContextVar = (selectedValue: string) => {
    const newModelConfig = produce(modelConfig, (draft) => {
      draft.configs.prompt_variables = modelConfig.configs.prompt_variables.map(
        (item) => {
          return {
            ...item,
            is_context_var: item.key === selectedValue,
          };
        },
      );
    });
    setModelConfig(newModelConfig);
  };

  return (
    <FeaturePanel
      className="mt-3"
      headerIcon={Icon}
      title="功能设置"
      headerRight={
        <div className="flex items-center gap-1">
          <ParamsConfig />
        </div>
      }
      hasHeaderBottomBorder={!hasData}
      noBodySpacing
    >
      {setting.category ||
      setting.func_name ||
      (setting.cmd && setting.cmd.split && setting.cmd.split("/")[1]) ||
      setting.match_list.length > 0 ||
      setting.is_robot ? (
        setting.is_robot ? (
          <div className="mt-1 px-3 pb-3">
            <div className="pt-2 pb-1 text-xs text-gray-500">
              <div
                className={
                  "inline-flex items-center px-2 h-6 rounded-md border border-[#FDB022] text-xs text-[#93370D]"
                }
              >
                <div
                  className={`${style.robotIcon} inline-block text-[#93370D]`}
                />
                机器人
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-1 px-3 pb-3 ">
            {setting.chat_icon && (
              <>
                <div className="pb-1 text-xs text-gray-500">图标</div>
                <IconImg src={setting.chat_icon} />
              </>
            )}
            {setting.category && (
              <InputItem label="类别" value={setting.category} />
            )}
            {setting.func_name && (
              <InputItem label="功能名称" value={setting.func_name} />
            )}
            {setting.cmd.split("/")[1] && (
              <InputItem label="CMD" value={setting.cmd.split("/")[1]} />
            )}
            {setting.match_list && setting.match_list.length > 0 && (
              <>
                <div className="pb-1 text-xs text-gray-500">匹配信息</div>
                {setting.match_list.map((item, index) => (
                  <CardItem
                    key={item}
                    onRemove={onRemove}
                    index={index}
                    value={item}
                  />
                ))}
              </>
            )}
          </div>
        )
      ) : (
        <div className="mt-1 px-3 pb-3">
          <div className="pt-2 pb-1 text-xs text-gray-500">
            设置该聊天的命中数据集、CMD、类型及是否机器人信息
          </div>
        </div>
      )}

      {/* {mode === AppType.completion && dataSet.length > 0 && (
        <ContextVar
          value={selectedContextVar?.key}
          options={promptVariablesToSelect}
          onChange={handleSelectContextVar}
        />
      )} */}
    </FeaturePanel>
  );
};
export default React.memo(DatasetConfig);
