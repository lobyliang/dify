'use client'
import type { FC } from 'react'
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash03 } from '@/app/components/base/icons/src/vender/line/general'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'

type ItemProps = {
  value: string
  index: number
  onRemove: (id: number) => void
}

const Item: FC<ItemProps> = ({
  value,
  index,
  onRemove,
}) => {
  const { t } = useTranslation()

  const media = useBreakpoints()
  const isMobile = media === MediaType.mobile

  const [showSettingsModal, setShowSettingsModal] = useState(false)

  return (
    <div className='group relative flex items-center mb-1 last-of-type:mb-0  pl-2.5 py-2 pr-3 w-full bg-white rounded-lg border-[0.5px] border-gray-200 shadow-xs'>
      <div className='grow'>
        <div className='flex items-center h-[18px]'>
          <div className='grow text-[13px] font-medium text-gray-800 truncate' title={value}>{value}</div>
        </div>
      </div>
      <div className='hidden group-hover:flex items-center justify-end absolute right-0 top-0 bottom-0 pr-2 w-[124px] bg-gradient-to-r from-white/50 to-white to-50%'>
        <div
          className='group/action flex items-center justify-center w-6 h-6 hover:bg-[#FEE4E2] rounded-md cursor-pointer'
          onClick={() => onRemove(index)}
        >
          <Trash03 className='w-4 h-4 text-gray-500 group-hover/action:text-[#D92D20]' />
        </div>
      </div>
    </div>
  )
}

export default Item
