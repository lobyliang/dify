'use client'
import type { FC } from 'react'
import React from 'react'
import Divider from '@/app/components/base/divider'
import CopyFeedback from '@/app/components/base/copy-feedback'
import { randomString } from '@/utils'

export type ICardItemProps = {
  label: string
  value: string
}
const CardItem: FC<ICardItemProps> = ({
  label,
  value,
}) => {
  return (
    <div className="py-1">
      <div className="pb-1 text-xs text-gray-500">{label}</div>
      <div className="w-full h-9 pl-2 pr-0.5 py-0.5 bg-black bg-opacity-[0.02] rounded-lg border border-black border-opacity-5 justify-start items-center inline-flex">
        <div className="h-4 px-2 justify-start items-start gap-2 flex flex-1 min-w-0">
          <div className="text-gray-700 text-xs font-medium text-ellipsis overflow-hidden whitespace-nowrap">
            {value}
          </div>
        </div>
        <Divider type="vertical" className="!h-3.5 shrink-0 !mx-0.5" />
        <CopyFeedback
          content={value}
          selectorId={randomString(8)}
          className={'hover:bg-gray-200'}
        />
      </div>
    </div>
  )
}
export default React.memo(CardItem)
