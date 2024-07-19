"use client";
import type { FC } from "react";
import React from "react";
import cn from "classnames";
import { ChevronDown } from "@/app/components/base/icons/src/vender/line/arrows";
import Popover from "@/app/components/base/popover";

export type ILanguageSelectProps = {
  currentLanguage: string;
  onSelect: (language: string) => void;
};

const LanguageSelect: FC<ILanguageSelectProps> = ({
  currentLanguage,
  onSelect,
}) => {
  return (
    <Popover
      manualClose
      trigger="click"
      htmlContent={
        <div className="w-full py-1">
          <div
            className="py-2 px-3 mx-1 flex items-center gap-2 hover:bg-gray-100 rounded-lg cursor-pointer text-gray-700 text-sm"
            onClick={() => onSelect("ai")}
          >
            AI模式
          </div>
          <div
            className="py-2 px-3 mx-1 flex items-center gap-2 hover:bg-gray-100 rounded-lg cursor-pointer text-gray-700 text-sm"
            onClick={() => onSelect("normal")}
          >
            普通模式
          </div>
        </div>
      }
      btnElement={
        <div className="inline-flex items-center">
          <span className="pr-[2px] text-xs leading-[18px] font-medium">
            {currentLanguage === "ai" ? "AI模式" : "普通模式"}
          </span>
          <ChevronDown className="w-3 h-3 opacity-60" />
        </div>
      }
      btnClassName={(open) =>
        cn(
          "!border-0 !px-0 !py-0 !bg-inherit !hover:bg-inherit",
          open ? "text-blue-600" : "text-gray-500",
        )
      }
      className="!w-[120px] h-fit !z-20 !translate-x-0 !left-[-16px]"
    />
  );
};
export default React.memo(LanguageSelect);
