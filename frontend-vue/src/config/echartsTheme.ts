/**ECharts 品牌深色主题（与 theme.ts 同源）。
 *
 * 在 bootstrap 中注册一次，组件统一用 echarts.init(el, ECHARTS_THEME)，
 * 不再各自写轴线/tooltip/文字颜色。
 */
import * as echarts from 'echarts'
import { theme } from './theme'

export const ECHARTS_THEME = 'brand-dark'

const c = theme.color

echarts.registerTheme(ECHARTS_THEME, {
  color: [
    c.accent.cyan,
    c.accent.blue,
    c.accent.violet,
    c.accent.amber,
    c.accent.green,
    c.accent.red,
  ],
  backgroundColor: 'transparent',
  textStyle: {
    color: c.text.secondary,
    fontFamily: theme.fontFamily.sans,
    fontSize: theme.font.sm,
  },
  title: {
    textStyle: { color: c.text.primary, fontSize: theme.font.md, fontWeight: 600 },
    subtextStyle: { color: c.text.muted, fontSize: theme.font.xs },
  },
  legend: {
    textStyle: { color: c.text.secondary, fontSize: theme.font.xs },
    itemWidth: 10,
    itemHeight: 8,
  },
  tooltip: {
    backgroundColor: 'rgba(10, 26, 54, 0.92)',
    borderColor: c.border.base,
    borderWidth: 1,
    textStyle: { color: c.text.primary, fontSize: theme.font.xs },
    axisPointer: {
      lineStyle: { color: c.border.base },
      crossStyle: { color: c.border.base },
      shadowStyle: { color: 'rgba(64, 158, 255, 0.08)' },
    },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: c.border.soft } },
    axisTick: { show: false },
    axisLabel: { color: c.text.muted, fontSize: theme.font.xs },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: c.text.muted, fontSize: theme.font.xs },
    splitLine: { lineStyle: { color: 'rgba(64, 158, 255, 0.08)' } },
  },
  timeAxis: {
    axisLine: { lineStyle: { color: c.border.soft } },
    axisLabel: { color: c.text.muted, fontSize: theme.font.xs },
    splitLine: { show: false },
  },
  line: {
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 2 },
  },
  bar: {
    barMaxWidth: 22,
  },
})
