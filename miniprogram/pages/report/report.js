const { request } = require('../../utils/request')
const { buildApiUrl } = require('../../utils/api-url')

const SECTION_KEYS = [
  ['summary', '客户总览与销售结论'],
  ['overview', '客户概况'],
  ['business_model', '业务模式与主打产品'],
  ['growth', '增量情况分析'],
  ['revenue_payment', '营收与付费能力'],
  ['digitalization', '数字化与在线教学现状'],
  ['competitor_guess', '竞品使用情况推断'],
  ['risks', '风险与注意事项'],
  ['info_note', '信息来源说明']
]

// 后端 stage 文案 → 步骤条短标签（顺序即流程顺序）
const STAGE_STEPS = [
  ['正在联网搜索客户公开信息…', '联网搜索'],
  ['正在整理客户事实档案…', '事实整理'],
  ['正在进行销售导向分析…', '销售分析'],
  ['正在生成 Word 报告…', 'Word 报告'],
  ['正在生成个性化解决方案…', '解决方案']
]

Page({
  data: {
    taskId: 0,
    status: 'loading', // loading / running / done / failed
    stage: '',
    error: '',
    customerName: '',
    customerTypeLabel: '',
    rating: '',
    ratingReason: '',
    sections: [],
    sales: null,
    facts: [],
    solution: null,
    downloading: false,
    downloadingSolution: false,
    steps: [],
    elapsedText: '',
    // 报告反馈闭环
    feedbackRating: '',        // '' / 'useful' / 'needs_improvement'
    feedbackComment: '',
    feedbackSubmitted: false,  // 是否已提交过
    submittingFeedback: false
  },

  onLoad(options) {
    this.setData({ taskId: Number(options.id) })
    this.poll()
  },

  onUnload() {
    if (this.timer) clearTimeout(this.timer)
    if (this.tick) clearInterval(this.tick)
  },

  buildSteps(stage) {
    const idx = STAGE_STEPS.findIndex(([text]) => text === stage)
    const current = idx === -1 ? 0 : idx
    return STAGE_STEPS.map(([text, label], i) => ({
      label,
      state: i < current ? 'done' : i === current ? 'current' : 'todo'
    }))
  },

  startTick(created_at) {
    if (this.tick) return
    this._created = created_at || Math.floor(Date.now() / 1000)
    const update = () => {
      const sec = Math.max(Math.floor(Date.now() / 1000) - this._created, 0)
      const m = Math.floor(sec / 60)
      const s = sec % 60
      this.setData({ elapsedText: m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒` })
    }
    update()
    this.tick = setInterval(update, 1000)
  },

  async poll() {
    try {
      const task = await request(`/api/analysis/${this.data.taskId}`)
      if (task.status === 'done') {
        if (this.tick) clearInterval(this.tick)
        this.renderReport(task)
      } else if (task.status === 'failed') {
        if (this.tick) clearInterval(this.tick)
        this.setData({ status: 'failed', error: task.error || '分析失败，请重试' })
      } else {
        this.setData({
          status: 'running',
          stage: task.stage || '排队中…',
          steps: this.buildSteps(task.stage)
        })
        this.startTick(task.created_at)
        this.timer = setTimeout(() => this.poll(), 3000)
      }
    } catch (err) {
      this.setData({ status: 'failed', error: err.message })
    }
  },

  renderReport(task) {
    const analysis = task.analysis || {}
    const rating = analysis.ka_rating || {}
    const sections = SECTION_KEYS
      .filter(([key]) => analysis[key])
      .map(([key, title]) => ({ title, content: analysis[key] }))
    this.setData({
      status: 'done',
      customerName: task.customer_name,
      customerTypeLabel: task.customer_type === 'teacher' ? '个体教师' : '教培机构',
      rating: rating.level || '',
      ratingReason: rating.reason || '',
      sections,
      sales: analysis.sales_direction || null,
      facts: ((task.profile && task.profile.facts) || []).map((fact) =>
        typeof fact === 'object' ? fact.fact : fact
      ),
      solution: task.solution && task.solution.title ? task.solution : null
    })
    this.loadFeedback()
  },

  onDownload() {
    if (this.data.downloading) return
    let url
    try {
      url = buildApiUrl(`/api/analysis/${this.data.taskId}/docx`)
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' })
      return
    }
    this.setData({ downloading: true })
    wx.showLoading({ title: '下载中…' })
    wx.downloadFile({
      url,
      header: { Authorization: `Bearer ${wx.getStorageSync('token')}` },
      success: (res) => {
        wx.hideLoading()
        if (res.statusCode !== 200) {
          wx.showToast({ title: '下载失败', icon: 'none' })
          return
        }
        wx.openDocument({
          filePath: res.tempFilePath,
          fileType: 'docx',
          showMenu: true,
          fail: () => wx.showToast({ title: '打开失败，请重试', icon: 'none' })
        })
      },
      fail: () => {
        wx.hideLoading()
        wx.showToast({ title: '下载失败，请检查网络', icon: 'none' })
      },
      complete: () => this.setData({ downloading: false })
    })
  },

  onDownloadSolution() {
    if (this.data.downloadingSolution) return
    let url
    try {
      url = buildApiUrl(`/api/analysis/${this.data.taskId}/solution-docx`)
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' })
      return
    }
    this.setData({ downloadingSolution: true })
    wx.showLoading({ title: '下载中…' })
    wx.downloadFile({
      url,
      header: { Authorization: `Bearer ${wx.getStorageSync('token')}` },
      success: (res) => {
        wx.hideLoading()
        if (res.statusCode !== 200) {
          wx.showToast({ title: '下载失败', icon: 'none' })
          return
        }
        wx.openDocument({
          filePath: res.tempFilePath,
          fileType: 'docx',
          showMenu: true,
          fail: () => wx.showToast({ title: '打开失败，请重试', icon: 'none' })
        })
      },
      fail: () => {
        wx.hideLoading()
        wx.showToast({ title: '下载失败，请检查网络', icon: 'none' })
      },
      complete: () => this.setData({ downloadingSolution: false })
    })
  },

  async loadFeedback() {
    try {
      const res = await request(`/api/analysis/${this.data.taskId}/feedback`)
      const fb = res.feedback
      if (fb) {
        this.setData({
          feedbackRating: fb.rating || '',
          feedbackComment: fb.comment || '',
          feedbackSubmitted: true
        })
      }
    } catch (err) {
      // 反馈回显失败不影响主报告展示，静默忽略
    }
  },

  onPickRating(e) {
    const rating = e.currentTarget.dataset.rating
    this.setData({ feedbackRating: rating, feedbackSubmitted: false })
  },

  onFeedbackInput(e) {
    this.setData({ feedbackComment: e.detail.value })
  },

  async submitFeedback() {
    const { feedbackRating, feedbackComment, submittingFeedback } = this.data
    if (submittingFeedback) return
    if (!feedbackRating) {
      wx.showToast({ title: '请先选择「有用」或「需改进」', icon: 'none' })
      return
    }
    this.setData({ submittingFeedback: true })
    try {
      await request(`/api/analysis/${this.data.taskId}/feedback`, {
        method: 'POST',
        data: { rating: feedbackRating, comment: (feedbackComment || '').trim() }
      })
      this.setData({ feedbackSubmitted: true })
      wx.showToast({ title: '已收到，谢谢反馈', icon: 'success' })
    } catch (err) {
      wx.showToast({ title: err.message || '提交失败', icon: 'none' })
    } finally {
      this.setData({ submittingFeedback: false })
    }
  },

  onRetry() {
    wx.navigateBack()
  },

  async onCancel() {
    try {
      await request(`/api/analysis/${this.data.taskId}/cancel`, { method: 'POST' })
      if (this.timer) clearTimeout(this.timer)
      if (this.tick) clearInterval(this.tick)
      wx.showToast({ title: '已取消', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 600)
    } catch (err) {
      wx.showToast({ title: err.message || '取消失败', icon: 'none' })
    }
  }
})
