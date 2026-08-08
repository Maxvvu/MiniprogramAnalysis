const { request } = require('./request')

/**
 * 微信登录：wx.login 拿 code → 后端换 openid → 存应用 Token
 */
function login() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        if (!res.code) {
          reject(new Error('微信登录失败，请重试'))
          return
        }
        try {
          const data = await request('/api/auth/wx-login', {
            method: 'POST',
            data: { code: res.code },
            auth: false
          })
          wx.setStorageSync('token', data.token)
          wx.setStorageSync('userId', data.user_id)
          wx.setStorageSync('isAdmin', !!data.is_admin)
          resolve(data)
        } catch (err) {
          reject(err)
        }
      },
      fail: () => reject(new Error('微信登录失败，请重试'))
    })
  })
}

/**
 * 检查当前 Token 是否有效，无效则重新登录
 */
async function ensureLogin() {
  const token = wx.getStorageSync('token')
  if (!token) return login()
  try {
    const me = await request('/api/auth/me')
    wx.setStorageSync('isAdmin', !!me.is_admin)
    return true
  } catch (err) {
    return login()
  }
}

module.exports = { login, ensureLogin }
