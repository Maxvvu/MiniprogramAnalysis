const { buildApiUrl } = require('./api-url')

/**
 * 统一请求封装：自动带 Token、统一错误处理
 */
function request(path, { method = 'GET', data = {}, auth = true } = {}) {
  return new Promise((resolve, reject) => {
    const url = buildApiUrl(path)
    const header = { 'Content-Type': 'application/json' }
    const token = wx.getStorageSync('token')
    if (auth && token) header['Authorization'] = `Bearer ${token}`
    wx.request({
      url,
      method,
      data,
      header,
      timeout: 30000,
      success: (res) => {
        if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.redirectTo({ url: '/pages/login/login' })
          reject(new Error('未登录'))
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(new Error(res.data.detail || `请求失败(${res.statusCode})`))
        }
      },
      fail: (err) => reject(new Error('网络异常，请检查后端服务是否启动'))
    })
  })
}

module.exports = { request }
