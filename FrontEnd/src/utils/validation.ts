import type { FormItemRule } from 'element-plus'

export function validateUsername(_rule: unknown, value: string, callback: (err?: Error) => void): void {
  if (!value) return callback()
  const val = value.trim()
  if (val.length < 6 || val.length > 32) return callback(new Error('用户名长度需在 6-32 位之间'))
  if (!/^[a-zA-Z0-9_]{6,32}$/.test(val)) return callback(new Error('用户名只能包含字母、数字和下划线'))
  callback()
}

export function validatePassword(_rule: unknown, value: string, callback: (err?: Error) => void): void {
  if (!value) return callback()
  if (value.length < 6 || value.length > 128) return callback(new Error('密码长度需在 6-128 位之间'))
  if (!/[A-Z]/.test(value)) return callback(new Error('密码必须包含至少一个大写字母'))
  if (!/[a-z]/.test(value)) return callback(new Error('密码必须包含至少一个小写字母'))
  if (!/\d/.test(value)) return callback(new Error('密码必须包含至少一个数字'))
  callback()
}

export function validateConfirmPassword(passwordRef: () => string) {
  return (_rule: unknown, value: string, callback: (err?: Error) => void): void => {
    if (!value) return callback()
    if (value !== passwordRef()) return callback(new Error('两次输入的密码不一致'))
    callback()
  }
}

export const usernameRule: FormItemRule = {
  required: true, message: '请输入用户名', trigger: 'blur',
}

export const passwordRule: FormItemRule = {
  required: true, message: '请输入密码', trigger: 'blur',
}
