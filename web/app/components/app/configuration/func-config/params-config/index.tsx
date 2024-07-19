'use client'
import type { FC } from 'react'
import React, { memo, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useContext } from 'use-context-selector'
import cn from 'classnames'
import IconImg from '../icon-img'
import { Settings04 } from '@/app/components/base/icons/src/vender/line/general'
import ConfigContext from '@/context/debug-configuration'
import Modal from '@/app/components/base/modal'
import Button from '@/app/components/base/button'
import type { FuncSetting } from '@/models/debug'
import RadioGroup from '@/app/components/app/configuration/config-vision/radio-group'
import { categoriesList } from '@/service/chat_robot'
import { SimpleSelect } from '@/app/components/base/select'

type item = {
  name: string
  value: string
}

type settingConfig = {
  matchText?: string
} & FuncSetting
const ParamsConfig: FC = () => {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { setSetting, setting } = useContext(ConfigContext)
  const [categoryList, setCategoryList] = useState<item[]>([])
  const [tempSettingConfigs, setTempSettingConfigs] = useState<settingConfig>({
    ...setting,
    matchText: '',
  })

  const onChange = (field: string) => {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setTempSettingConfigs(item => ({ ...item, [field]: e.target.value }))
    }
  }

  const getCategoriesList = () => {
    categoriesList().then((res) => {
      const list = res.map((item) => {
        return {
          value: item.category,
          name: item.name,
        }
      })
      setCategoryList(list)
    })
  }

  const isValid = () => {
    // let errMsg = ''
    // if (tempDataSetConfigs.retrieval_model === RETRIEVE_TYPE.multiWay) {
    //   if (!tempDataSetConfigs.reranking_model?.reranking_model_name && (!rerankDefaultModel && isRerankDefaultModelVaild))
    //     errMsg = t('appDebug.datasetConfig.rerankModelRequired')
    // }
    // if (errMsg) {
    //   Toast.notify({
    //     type: 'error',
    //     message: errMsg,
    //   })
    // }
    // return !errMsg
  }
  const handleSave = () => {
    const config = { ...tempSettingConfigs }
    if (config.matchText) {
      config.match_list = config.matchText
        .split('\n')
        .map(item => item.trim())
        .filter(item => item !== '')
    }
    config.cmd = `${config.category}/${config.cmd}`
    delete config.matchText
    if (config.is_robot) {
      config.category = ''
      config.cmd = ''
      config.func_name = ''
      config.match_list = []
    }
    setSetting(config)
    setOpen(false)
  }

  useEffect(() => {
    getCategoriesList()
  }, [])

  return (
    <div>
      <div
        className={cn(
          'flex items-center rounded-md h-7 px-3 space-x-1 text-gray-700 cursor-pointer hover:bg-gray-200',
          open && 'bg-gray-200',
        )}
        onClick={() => {
          setTempSettingConfigs({
            ...setting,
            cmd: setting.cmd.split('/')[1] || '',
            matchText: setting.match_list.join('\n'),
          })
          setOpen(true)
        }}
      >
        <Settings04 className="w-[14px] h-[14px]" />
        <div className="text-xs font-medium">设置</div>
      </div>
      {open && (
        <Modal
          isShow={open}
          onClose={() => {
            setOpen(false)
          }}
          className="sm:min-w-[528px]"
          wrapperClassName="z-50"
          title="功能设置"
        >
          <div className="mt-2 space-y-3">
            <div className={'mt-6 font-medium  text-gray-900'}>是否机器人</div>
            <div className="flex mt-2">
              <RadioGroup
                className="space-x-3"
                options={[
                  {
                    label: '是',
                    value: true,
                  },
                  {
                    label: '否',
                    value: false,
                  },
                ]}
                value={tempSettingConfigs.is_robot}
                onChange={function (value: boolean): void {
                  setTempSettingConfigs({
                    ...tempSettingConfigs,
                    is_robot: value,
                  })
                }}
              />
            </div>
            {!tempSettingConfigs.is_robot && (
              <>
                <div
                  className={
                    'mt-6 font-medium  text-gray-900 flex items-center justify-between'
                  }
                >
                  <span>图标</span>
                  {tempSettingConfigs.chat_icon && (
                    <IconImg src={tempSettingConfigs.chat_icon} />
                  )}
                </div>
                <div className="flex mt-2">
                  <input
                    className={
                      'flex-grow rounded-lg h-10 box-border px-3 bg-gray-100'
                    }
                    value={tempSettingConfigs.chat_icon}
                    onChange={onChange('chat_icon')}
                    placeholder="请输入图标地址"
                  />
                </div>
                <div className={'mt-6 font-medium  text-gray-900'}>类别</div>
                <div className="mt-2">
                  <SimpleSelect
                    defaultValue={tempSettingConfigs.category}
                    className='w-full'
                    items={categoryList}
                    onSelect={(item) => {
                      setTempSettingConfigs(
                        {
                          ...tempSettingConfigs,
                          category: item.value.toString(),
                        })
                    }}
                  />
                </div>
                <div className={'mt-6 font-medium  text-gray-900'}>
                  功能名称
                </div>
                <div className="flex mt-2">
                  <input
                    className={
                      'flex-grow rounded-lg h-10 box-border px-3 bg-gray-100'
                    }
                    value={tempSettingConfigs.func_name}
                    onChange={onChange('func_name')}
                    placeholder="请输入功能名称"
                    maxLength={8}
                  />
                </div>
                <div className={'mt-6 font-medium  text-gray-900'}>CMD命令</div>
                <div className="flex mt-2">
                  <input
                    className={
                      'flex-grow rounded-lg h-10 box-border px-3 bg-gray-100'
                    }
                    value={tempSettingConfigs.cmd}
                    onChange={onChange('cmd')}
                    placeholder="请输入CMD命令"
                    maxLength={30}
                  />
                </div>
                <div className={'mt-6 font-medium  text-gray-900'}>
                  匹配信息
                </div>
                <div className="flex mt-2">
                  <textarea
                    rows={8}
                    className={
                      'pt-2 pb-2 px-3 rounded-lg bg-gray-100 w-full text-gray-900'
                    }
                    value={tempSettingConfigs.matchText}
                    onChange={onChange('matchText')}
                    placeholder="请输入匹配信息"
                    style={{ resize: 'none' }}
                  />
                </div>
              </>
            )}
          </div>
          <div className="mt-6 flex justify-end">
            <Button
              className="mr-2 flex-shrink-0"
              onClick={() => {
                setOpen(false)
              }}
            >
              {t('common.operation.cancel')}
            </Button>
            <Button
              type="primary"
              className="flex-shrink-0"
              onClick={handleSave}
            >
              {t('common.operation.save')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
export default memo(ParamsConfig)
