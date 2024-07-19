import { get, post, del } from '@/service/base'
import type { SegFileInfo, File, BindSegFile } from '@/app/components/base/file-upload/type'

export const filesUpload = (body: any) => {
  return post<File>('/chunckAttach/files/upload', { body }, { base: '/v1', bodyStringify: false, deleteContentType: true })
}

export const fetchFilesList = (ids: string) => {
  return get<File>('/chunckAttach/files/info/' + ids, {}, { base: '/v1' })
}


export const fetchSegFile = (segId: string) => {
  return get<SegFileInfo>(`/chunckAttach/files/${segId}/infos`, {}, { base: '/v1' })
}

export const bindSegFile = (segId: string, body: any) => {
  return post<BindSegFile>(`/chunckAttach/files/${segId}/bind`, { body }, { base: '/v1' })
}

export const deleteBindSegFile = (segId: string, body: any) => {
  return del(`/chunckAttach/files/${segId}/bind`, { body }, { base: '/v1' })
}

export const fetchBillingUrl = () => {
  return get<{ url: string }>('/billing/invoices')
}
