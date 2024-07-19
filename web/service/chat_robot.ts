import { get } from './base'
import type { ChatCategory } from '@/types/app'

export const categoriesList = () => {
  return get<ChatCategory[]>('/chat_robot/categories/list', {})
}
