<template>
  <main class="wrap">
    <section class="hero">
      <div><h1>A股投研 HTML 页面中心</h1><p>行情复盘 / 量化因子 / 板块个股 / 多智能体投研，一键刷新当日页面。</p></div>
      <div class="actions"><input v-model="sector" placeholder="板块名称，如 光伏设备"/><button @click="refreshAll" :disabled="loading">{{ loading ? '生成中...' : '刷新全部' }}</button></div>
    </section>
    <section class="quick">
      <button @click="generate('market_replay')">大盘复盘</button>
      <button @click="generate('quant_factor')">量化因子</button>
      <button @click="generate('sector_stock')">板块个股</button>
      <button @click="generate('agent_debate')">多智能体</button>
    </section>
    <section class="grid"><a v-for="r in reports" :key="r.filename" class="card" :href="apiBase + r.url" target="_blank"><b>{{ r.filename }}</b><span>{{ r.mtime }}</span></a></section>
  </main>
</template>
<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'
const apiBase = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8787'
const reports = ref<any[]>([])
const loading = ref(false)
const sector = ref('光伏设备')
async function loadReports(){ reports.value = (await axios.get(apiBase + '/api/reports')).data }
async function refreshAll(){ loading.value=true; try{ await axios.get(apiBase + '/api/reports/refresh-all',{params:{sector:sector.value}}); await loadReports() } finally{ loading.value=false } }
async function generate(report_type:string){ loading.value=true; try{ await axios.post(apiBase + '/api/reports/generate',null,{params:{report_type,sector:sector.value}}); await loadReports() } finally{ loading.value=false } }
onMounted(loadReports)
</script>
