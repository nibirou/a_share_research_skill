<template>
  <main class="wrap">
    <section class="hero">
      <div>
        <h1>A股投研 HTML 页面中心</h1>
        <p>行情复盘、量化因子、板块个股、资金轮动、聪明资金、估值诊断、趋势共振、自选股、指数 ETF、流动性、催化日历、事件风险、产业链、海外映射、多智能体，一键刷新。</p>
      </div>
      <div class="actions">
        <input v-model="sector" placeholder="目标板块/股票/观察对象，如 光伏设备" />
        <button @click="refreshAll" :disabled="loading">{{ loading ? '生成中...' : '刷新全部' }}</button>
      </div>
    </section>

    <section class="quick">
      <button v-for="item in reportTypes" :key="item.id" @click="generate(item.id)" :disabled="loading">
        {{ item.label }}
      </button>
    </section>

    <section class="grid">
      <a v-for="r in reports" :key="r.filename" class="card" :href="apiBase + r.url" target="_blank">
        <b>{{ r.filename }}</b>
        <span>{{ r.mtime }}</span>
      </a>
    </section>
  </main>
</template>

<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8787'
const reports = ref<any[]>([])
const loading = ref(false)
const sector = ref('光伏设备')

const reportTypes = [
  { id: 'market_replay', label: '大盘复盘' },
  { id: 'quant_factor', label: '量化因子' },
  { id: 'sector_stock', label: '板块个股' },
  { id: 'sector_flow_rotation', label: '资金轮动' },
  { id: 'smart_money_clusters', label: '聪明资金' },
  { id: 'sector_valuation_diagnosis', label: '估值诊断' },
  { id: 'trend_resonance', label: '趋势共振' },
  { id: 'watchlist_terminal', label: '自选股终端' },
  { id: 'index_etf_monitor', label: '指数 ETF' },
  { id: 'liquidity_dashboard', label: '流动性' },
  { id: 'earnings_catalyst_calendar', label: '催化日历' },
  { id: 'single_stock_event_risk', label: '事件风险' },
  { id: 'industry_chain_map', label: '产业链图谱' },
  { id: 'global_mapping', label: '海外映射' },
  { id: 'agent_debate', label: '多智能体' },
]

async function loadReports() {
  reports.value = (await axios.get(apiBase + '/api/reports')).data
}

async function refreshAll() {
  loading.value = true
  try {
    await axios.get(apiBase + '/api/reports/refresh-all', { params: { sector: sector.value } })
    await loadReports()
  } finally {
    loading.value = false
  }
}

async function generate(report_type: string) {
  loading.value = true
  try {
    await axios.post(apiBase + '/api/reports/generate', null, { params: { report_type, sector: sector.value } })
    await loadReports()
  } finally {
    loading.value = false
  }
}

onMounted(loadReports)
</script>
