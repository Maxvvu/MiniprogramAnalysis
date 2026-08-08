const { request } = require('../../utils/request')
const { ensureLogin } = require('../../utils/auth')

Page({
  data: {
    tab: 'overview', // overview / settings / knowledge
    stats: null,
    users: [],
    allUsers: [],
    searchKey: '',
    globalLimit: 5,
    settings: null,
    knowledge: [],
    // 知识库新增表单
    kTitle: '',
    kCategory: 'general',
    kContent: '',
    saving: false,
    // 报告反馈
    feedback: [],
    feedbackFilter: 'pending'
  },

  async onShow() {
    try {
      await ensureLogin()
    } catch (err) {
      wx.redirectTo({ url: '/pages/login/login' })
      return
    }
    if (!wx.getStorageSync('isAdmin')) {
      wx.showToast({ title: '无管理权限', icon: 'none' })
      setTimeout(() => wx.navigateBack(), 800)
      return
    }
    this.loadTab()
  },

  switchTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
    this.loadTab()
  },

  loadTab() {
    const t = this.data.tab
    if (t === 'overview') this.loadOverview()
    else if (t === 'settings') this.loadSettings()
    else if (t === 'feedback') this.loadFeedback()
    else this.loadKnowledge()
  },

  async loadOverview() {
    try {
      const [stats, users] = await Promise.all([
        request('/api/admin/stats'),
        request('/api/admin/users')
      ])
      const allUsers = (users.items || []).map((u) => ({
        ...u,
        createdText: this._fmt(u.created_at),
        editQuota: u.quota_override == null ? '' : String(u.quota_override)
      }))
      this.setData({ stats, globalLimit: users.global_limit, allUsers })
      this.filterUsers()
    } catch (err) {
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },

  _fmt(ts) {
    if (!ts) return ''
    const d = new Date(ts * 1000)
    const p = (n) => (n < 10 ? '0' : '') + n
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  },

  onSearchInput(e) {
    this.setData({ searchKey: e.detail.value })
    this.filterUsers()
  },

  filterUsers() {
    const key = (this.data.searchKey || '').trim().toLowerCase()
    const list = key
      ? this.data.allUsers.filter((u) =>
          String(u.id).includes(key) ||
          (u.nickname || '').toLowerCase().includes(key) ||
          (u.real_name || '').toLowerCase().includes(key) ||
          (u.phone || '').includes(key) ||
          (u.openid || '').toLowerCase().includes(key))
      : this.data.allUsers
    this.setData({ users: list })
  },

  onQuotaInput(e) {
    const id = Number(e.currentTarget.dataset.id)
    const users = this.data.users.map((u) => (u.id === id ? { ...u, editQuota: e.detail.value } : u))
    this.setData({ users })
  },

  async saveQuota(e) {
    const id = Number(e.currentTarget.dataset.id)
    const u = this.data.users.find((x) => x.id === id)
    const raw = (u.editQuota || '').trim()
    const override = raw === '' ? null : Number(raw)
    try {
      await request(`/api/admin/users/${id}/quota`, { method: 'POST', data: { override } })
      wx.showToast({ title: override == null ? '已恢复默认' : '已设置', icon: 'success' })
      this.loadOverview()
    } catch (err) {
      wx.showToast({ title: err.message || '设置失败', icon: 'none' })
    }
  },

  async loadSettings() {
    try {
      const settings = await request('/api/admin/settings')
      this.setData({ settings })
    } catch (err) {
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },

  onSettingInput(e) {
    const key = e.currentTarget.dataset.key
    this.setData({ [`settings.${key}`]: e.detail.value })
  },

  onSearchToggle(e) {
    this.setData({ 'settings.search_enabled': e.detail.value })
  },

  async saveSettings() {
    const s = this.data.settings
    const body = {}
    if (s.llm_base_url) body.llm_base_url = s.llm_base_url.trim()
    if (s.llm_model) body.llm_model = s.llm_model.trim()
    if (s.llm_api_key && !s.llm_api_key.includes('****')) body.llm_api_key = s.llm_api_key.trim()
    if (s.daily_free_limit !== '' && s.daily_free_limit != null) body.daily_free_limit = Number(s.daily_free_limit)
    if (typeof s.search_enabled === 'boolean') body.search_enabled = s.search_enabled
    if (Object.keys(body).length === 0) {
      wx.showToast({ title: '没有要修改的项', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    try {
      await request('/api/admin/settings', { method: 'POST', data: body })
      wx.showToast({ title: '已保存并生效', icon: 'success' })
      this.loadSettings()
    } catch (err) {
      wx.showToast({ title: err.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  async loadKnowledge() {
    try {
      const res = await request('/api/admin/knowledge')
      this.setData({ knowledge: res.items || [] })
    } catch (err) {
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },

  onKInput(e) {
    const key = e.currentTarget.dataset.key
    this.setData({ [key]: e.detail.value })
  },

  async addKnowledge() {
    const { kTitle, kCategory, kContent } = this.data
    if (!kTitle.trim() || kContent.trim().length < 20) {
      wx.showToast({ title: '标题必填，内容至少20字', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    try {
      await request('/api/admin/knowledge', {
        method: 'POST',
        data: { title: kTitle.trim(), category: kCategory.trim() || 'general', content: kContent.trim() }
      })
      wx.showToast({ title: '已添加', icon: 'success' })
      this.setData({ kTitle: '', kContent: '' })
      this.loadKnowledge()
    } catch (err) {
      wx.showToast({ title: err.message || '添加失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  async toggleKnowledge(e) {
    const { id, status } = e.currentTarget.dataset
    try {
      await request(`/api/admin/knowledge/${id}/status`, { method: 'POST', data: { status } })
      this.loadKnowledge()
    } catch (err) {
      wx.showToast({ title: err.message || '操作失败', icon: 'none' })
    }
  },

  async loadFeedback() {
    const RATING = { useful: '👍 有用', needs_improvement: '✍️ 需改进' }
    const STATUS = { pending: '待处理', adopted: '已入库', dismissed: '已忽略' }
    try {
      const res = await request(`/api/admin/feedback?status=${this.data.feedbackFilter}`)
      const items = (res.items || []).map((f) => ({
        ...f,
        ratingText: RATING[f.rating] || f.rating,
        statusText: STATUS[f.status] || f.status,
        typeText: f.customer_type === 'teacher' ? '个体教师' : '教培机构',
        createdText: this._fmt(f.created_at)
      }))
      this.setData({ feedback: items })
    } catch (err) {
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },

  switchFeedbackFilter(e) {
    this.setData({ feedbackFilter: e.currentTarget.dataset.filter })
    this.loadFeedback()
  },

  adoptFeedback(e) {
    const id = Number(e.currentTarget.dataset.id)
    wx.showModal({
      title: '采纳入库',
      content: '将把这条销售补充/纠正沉淀为知识库文档，供后续分析检索引用。确认？',
      success: async (r) => {
        if (!r.confirm) return
        try {
          const res = await request(`/api/admin/feedback/${id}/adopt`, { method: 'POST', data: {} })
          wx.showToast({ title: '已入库', icon: 'success' })
          this.loadFeedback()
        } catch (err) {
          wx.showToast({ title: err.message || '操作失败', icon: 'none' })
        }
      }
    })
  },

  dismissFeedback(e) {
    const id = Number(e.currentTarget.dataset.id)
    wx.showModal({
      title: '忽略反馈',
      content: '确认忽略这条反馈？（不会入库）',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await request(`/api/admin/feedback/${id}/dismiss`, { method: 'POST', data: {} })
          this.loadFeedback()
        } catch (err) {
          wx.showToast({ title: err.message || '操作失败', icon: 'none' })
        }
      }
    })
  }
})
