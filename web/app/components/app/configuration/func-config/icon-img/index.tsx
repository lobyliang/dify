'use client'
import type { FC } from 'react'
import React, { useEffect, useState } from 'react'

type ItemProps = {
  src: string
  className?: string
}

const Item: FC<ItemProps> = ({
  src,
  className = '',
}) => {
  const [imgSrc, setImgSrc] = useState('')
  const [isShowImage, setIsShowImage] = useState(true)

  // 图片加载错误
  const onError = (e: any) => {
    setIsShowImage(false)
  }

  // 判断是否是http链接
  function isHttpUrl(url: string) {
    const httpPrefix = 'http://'
    const httpsPrefix = 'https://'

    return url.startsWith(httpPrefix) || url.startsWith(httpsPrefix)
  }

  useEffect(() => {
    if (isHttpUrl(src)) {
      setImgSrc(src)
      setIsShowImage(true)
    }
  }, [src])

  return (isShowImage
    ? <img
      className={`w-6 aspect-square ${className}`}
      src={imgSrc}
      alt=""
      crossOrigin='anonymous'
      onError={onError}
    />
    : <></>
  )
}

export default Item
