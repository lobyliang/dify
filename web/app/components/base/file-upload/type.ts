import { StringGradients } from "antd/es/progress/progress"

export type File = {
  created_at: string
  created_by: string
  extension: string
  id: string
  mime_type: string
  name: string
  size: number
}

export type SegFile = {
  created_at: string
  created_by: string
  extension: string
  file: string
  file_name: StringGradients
  id: string
  mime_type: string
  size: number
  source: string
}

export type BindSegFile = {
  attach_type: string
  created_at: string
  created_by: string
  doc_seg_id: string
  extension: string
  file: string
  file_name: StringGradients
  id: string
  mime_type: string
  size: number
  source: string
  storage_type: string
}

export type SegFileInfo = {
  attach: SegFile[],
  cover: SegFile[],
}
