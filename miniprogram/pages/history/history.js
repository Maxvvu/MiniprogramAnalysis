const { request } = require('../../utils/request')
const { ensureLogin } = require('../../utils/auth')

const STATUS_MAP = {
  pending: { label: '排队中', color: '#8a919f' },
  running: { label: '分析中', color: '#2b6de5' },
  done: { label: '已完成', color: '#52c41a' },
  failed: { label: '失败', color: '#f5222d' }
}

Page({
  data: { items: [], allItems: [], searchKey: '', loading: true },

  async onShow() {
    try {
      await ensureLogin()
      const res = await request('/api/analysis')
      const allItems = (res.items || []).map((t) => {
        const status = STATUS_MAP[t.status] || STATUS_MAP.pending
        let rating = ''
        if (t.status === 'done' && t.analysis && t.analysis.ka_rating) {
          rating = t.analysis.ka_rating.level
        }
        return {
          ...t,
          rating,
          statusLabel: status.label,
          statusColor: status.color,
          typeLabel: t.customer_type === 'teacher' ? '个体教师' : '教培机构',
          timeText: formatTime(t.created_at)
        }
      })
      this.setData({ allItems, loading: false })
      this.filterItems()
    } catch (err) {
      this.setData({ loading: false })
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    }
  },

  onSearchInput(e) {
    this.setData({ searchKey: e.detail.value })
    this.filterItems()
  },

  filterItems() {
    const key = (this.data.searchKey || '').trim().toLowerCase()
    const list = key
      ? this.data.allItems.filter((t) => (t.customer_name || '').toLowerCase().includes(key))
      : this.data.allItems
    this.setData({ items: list })
  },

  onTapItem(e) {
    wx.navigateTo({ url: `/pages/report/report?id=${e.currentTarget.dataset.id}` })
  },

  onClearAll() {
    if (!this.data.allItems.length) return
    wx.showModal({
      title: '确认清空',
      content: `确定要清空全部 ${this.data.allItems.length} 条分析记录吗？此操作不可恢复。`,
      confirmText: '清空',
      confirmColor: '#f5222d',
      success: async (r) => {
        if (!r.confirm) return
        wx.showLoading({ title: '清空中...', mask: true })
        try {
          await request('/api/analysis/clear', { method: 'POST' })
          wx.hideLoading()
          this.setData({ items: [], allItems: [], searchKey: '' })
          wx.showToast({ title: '已清空', icon: 'success' })
        } catch (err) {
          wx.hideLoading()
          wx.showToast({ title: err.message || '清空失败', icon: 'none' })
        }
      }
    })
  },

  async onDelete(e) {
    const id = e.currentTarget.dataset.id
    const item = this.data.allItems.find((t) => t.id === id)
    if (!item) return
    wx.showModal({
      title: '删除记录',
      content: `确定要删除「${item.customer_name}」的分析记录吗？`,
      confirmText: '删除',
      confirmColor: '#f5222d',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await request(`/api/analysis/${id}`, { method: 'DELETE' })
          const allItems = this.data.allItems.filter((t) => t.id !== id)
          this.setData({ allItems })
          this.filterItems()
          wx.showToast({ title: '已删除', icon: 'success' })
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' })
        }
      }
    })
  }
})

function formatTime(ts) {
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
