const { login } = require('../../utils/auth')

Page({
  data: { loading: false },

  async onTapLogin() {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      await login()
      wx.switchTab({ url: '/pages/index/index' })
    } catch (err) {
      wx.showToast({ title: err.message || '登录失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
