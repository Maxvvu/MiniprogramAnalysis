const { request } = require('../../utils/request')
const { ensureLogin } = require('../../utils/auth')

Page({
  data: { items: [], loading: true },
  async onShow() {
    try {
      await ensureLogin()
      const res = await request('/api/customers')
      this.setData({ items: res.items || [], loading: false })
    } catch (err) {
      this.setData({ loading: false })
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },
  onTapCustomer(e) {
    wx.navigateTo({ url: `/pages/customer/customer?id=${e.currentTarget.dataset.id}` })
  }
})
