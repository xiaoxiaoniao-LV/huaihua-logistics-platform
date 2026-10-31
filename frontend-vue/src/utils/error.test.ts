import { describe, expect, it } from 'vitest'
import { apiError } from './error'

describe('apiError', () => {
  it('优先取 FastAPI 的字符串 detail', () => {
    const e = { response: { data: { detail: '资源待审核，需管理员审核通过后才能上架' } } }
    expect(apiError(e)).toBe('资源待审核，需管理员审核通过后才能上架')
  })

  it('合并 422 校验数组的 msg', () => {
    const e = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'password'], msg: '密码太短' },
            { loc: ['body', 'role'], msg: '角色不合法' },
          ],
        },
      },
    }
    expect(apiError(e)).toBe('密码太短；角色不合法')
  })

  it('没有 detail 时回退到 error.message', () => {
    expect(apiError(new Error('Network Error'))).toBe('Network Error')
  })

  it('完全无法识别时使用兜底文案', () => {
    expect(apiError({}, '保存失败')).toBe('保存失败')
  })
})
