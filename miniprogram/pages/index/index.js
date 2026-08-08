const { request } = require('../../utils/request')
const { ensureLogin } = require('../../utils/auth')

Page({
  data: {
    customerName: '',
    customerType: 'institution',
    extraNotes: '',
    submitting: false,
    quotaRemaining: null,
    isAdmin: false,
    showProfile: false,
    pName: '',
    pPhone: '',
    types: [
      { value: 'institution', label: '教培机构' },
      { value: 'teacher', label: '个体教师' }
    ]
  },

  async onShow() {
    try {
      await ensureLogin()
      this.setData({ isAdmin: !!wx.getStorageSync('isAdmin') })
      this.loadQuota()
      this.checkProfile()
    } catch (err) {
      wx.redirectTo({ url: '/pages/login/login' })
    }
  },

  async checkProfile() {
    try {
      const me = await request('/api/auth/me')
      if (me.need_profile) this.setData({ showProfile: true })
    } catch (err) {}
  },

  onProfileInput(e) {
    const key = e.currentTarget.dataset.key
    this.setData({ [key]: e.detail.value })
  },

  async onSubmitProfile() {
    const name = this.data.pName.trim()
    const phone = this.data.pPhone.trim()
    if (!name || !/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请填写姓名和正确手机号', icon: 'none' })
      return
    }
    try {
      await request('/api/auth/profile', { method: 'POST', data: { name, phone } })
      this.setData({ showProfile: false })
      wx.showToast({ title: '已保存', icon: 'success' })
    } catch (err) {
      wx.showToast({ title: err.message || '保存失败', icon: 'none' })
    }
  },

  async onSkipProfile() {
    this.setData({ showProfile: false })
    try {
      await request('/api/auth/profile-skip', { method: 'POST' })
    } catch (err) {}
  },

  onOpenAdmin() {
    wx.navigateTo({ url: '/pages/admin/admin' })
  },

  loadQuota() {
    request('/api/analysis/quota')
      .then((q) => {
        if (q && typeof q.remaining === 'number') {
          this.setData({ quotaRemaining: q.remaining })
        }
      })
      .catch(() => {})
  },

  onNameInput(e) {
    this.setData({ customerName: e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ extraNotes: e.detail.value })
  },

  onSelectType(e) {
    this.setData({ customerType: e.currentTarget.dataset.value })
  },

  async onSubmit() {
    const name = this.data.customerName.trim()
    if (!name) {
      wx.showToast({ title: '请输入客户名称', icon: 'none' })
      return
    }
    if (this.data.submitting) return
    if (this.data.quotaRemaining === 0) {
      wx.showToast({ title: '今日免费次数已用完，明天再来吧', icon: 'none' })
      return
    }
    // 先查是否有可复用的近期报告
    wx.showLoading({ title: '检查中...', mask: true })
    let hasRecent = false
    try {
      const recent = await request('/api/analysis/recent', {
        data: { customer_name: name, customer_type: this.data.customerType }
      })
      wx.hideLoading()
      if (recent && recent.task_id) {
        hasRecent = true
        wx.showModal({
          title: '发现近期报告',
          content: `该客户有 ${recent.days_ago} 天前的分析报告。\n查看旧报告不消耗次数；重新分析将联网获取最新信息并消耗 1 次。`,
          confirmText: '重新分析',
          cancelText: '查看旧报告',
          success: (r) => {
            if (r.confirm) this._doSubmit(true)
            else wx.navigateTo({ url: `/pages/report/report?id=${recent.task_id}` })
          },
          fail: () => {
            // 用户取消弹窗（如按返回键），直接走正常提交
            this._doSubmit(false)
          }
        })
      }
    } catch (err) {
      wx.hideLoading()
    }
    if (!hasRecent) this._doSubmit(false)
  },

  async _doSubmit(force) {
    this.setData({ submitting: true })
    try {
      const res = await request('/api/analysis', {
        method: 'POST',
        data: {
          customer_name: this.data.customerName.trim(),
          customer_type: this.data.customerType,
          extra_notes: this.data.extraNotes.trim(),
          force
        }
      })
      this.loadQuota()
      wx.showToast({ title: res.cached ? '已加载历史分析' : '已提交分析', icon: 'success' })
      setTimeout(() => {
        wx.navigateTo({ url: `/pages/report/report?id=${res.task_id}` })
      }, 600)
    } catch (err) {
      wx.showToast({ title: err.message || '提交失败', icon: 'none' })
    } finally {
      this.setData({ submitting: false })
    }
  }
})
