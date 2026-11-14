/**
 * Digest content and card chrome labels, in English or Simplified Chinese.
 *
 * Only the digest reply and its cards use these. The app shell, sidebar and
 * Settings stay English, and collected text (titles, quotes, model names) is
 * never translated.
 */

export type UiLang = 'en' | 'zh-CN'

/** Language for one entry: its saved language, else the legacy default by source. */
export function entryLang(outputLanguage: string | null | undefined, sourceKind: string): UiLang {
  if (outputLanguage === 'en' || outputLanguage === 'zh-CN') {
    return outputLanguage
  }
  return sourceKind === 'juya' || sourceKind === 'zhihu' ? 'zh-CN' : 'en'
}

/** A digest is Chinese only when every entry in it is Chinese. */
export function digestLang(langs: readonly UiLang[]): UiLang {
  return langs.length > 0 && langs.every((lang) => lang === 'zh-CN') ? 'zh-CN' : 'en'
}

const EN = {
  digestHead: 'Digest',
  digestMeta: '{items} items · {returned} of {total} sources returned results',
  item: 'item',
  items: 'items',
  connectorSuffix: ' connector:',
  windowPrefix: ':',
  settingsFor: '{label} settings',
  runAgain: 'Run again',
  repeatHelp:
    'Repeats the request behind {ref}: {summary}. Sources, counts, timeframe and language come from that request, not from current Settings.',
  summary: 'Summary',
  whyItMatters: 'Why it matters',
  background: 'Background',
  expand: 'Show details',
  collapse: 'Hide details',
  deepDive: 'Deep dive',
  askAbout: 'Ask about this',
  relatedChip: 'Related: #{n}',
  relatedAria: 'Related: entry #{n} names the same model',
  newModel: 'New model',
  freeTokenPricing: 'Free token pricing',
  specContext: 'Context',
  specInput: 'Input / 1M tokens',
  specOutput: 'Output / 1M tokens',
  githubToday: '+{n} today',
  leadStory: 'Lead story',
  hfRank: 'Rank',
  hfModel: 'Model',
  hfLink: 'Link',
  hfTrending: 'Trending',
  hfDownloads: '30-day downloads',
  hfLikes: 'Likes',
  hfPipeline: 'Pipeline',
  hfVariants: 'Variants',
  hfActions: 'Actions',
  hfOpen: 'Open {id} on Hugging Face',
  hfDeepAria: 'Deep dive: {title}',
  hfAskAria: 'Ask about this: {title}',
  hfNone: 'None reported',
  hfNote:
    'Trending score and downloads from the Hugging Face Hub API. “—” means no base model is declared.',
  trendingModels: 'Trending models',
  trendingRepos: 'Trending repositories',
  modelsYouCanCall: 'Models you can call',
  noItems: 'Connector returned no items for this request. Other sources completed normally.',
  windowNotice:
    'No models matched the requested window; showing matching listings from the last 7 days instead.',
} as const

export type LabelKey = keyof typeof EN

const ZH: Record<LabelKey, string> = {
  digestHead: '早报',
  digestMeta: '{items} 条 · {returned}/{total} 个来源有结果',
  item: '项',
  items: '项',
  connectorSuffix: '连接器：',
  windowPrefix: '：',
  settingsFor: '{label} 设置',
  runAgain: '重新运行',
  repeatHelp:
    '重复 {ref} 对应的请求：{summary}。来源、数量、时间范围和语言均来自该请求，而非当前设置。',
  summary: '摘要',
  whyItMatters: '为什么重要',
  background: '背景知识',
  expand: '展开详情',
  collapse: '收起详情',
  deepDive: '深入了解',
  askAbout: '追问这条',
  relatedChip: '相关：#{n}',
  relatedAria: '相关：第 {n} 条指向同一模型',
  newModel: '新模型',
  freeTokenPricing: '免费 token 定价',
  specContext: '上下文',
  specInput: '输入 / 每百万 tokens',
  specOutput: '输出 / 每百万 tokens',
  githubToday: '今日 +{n}',
  leadStory: '头条',
  hfRank: '排名',
  hfModel: '模型',
  hfLink: '链接',
  hfTrending: '热度',
  hfDownloads: '30 天下载',
  hfLikes: '点赞',
  hfPipeline: '任务类型',
  hfVariants: '变体',
  hfActions: '操作',
  hfOpen: '在 Hugging Face 打开 {id}',
  hfDeepAria: '深入了解：{title}',
  hfAskAria: '追问：{title}',
  hfNone: '未提供',
  hfNote: '热度与下载量来自 Hugging Face Hub API。“—”表示未声明基础模型。',
  trendingModels: '热门模型',
  trendingRepos: '热门仓库',
  modelsYouCanCall: '可调用的模型',
  noItems: '该连接器本次请求没有返回条目，其他来源已正常完成。',
  windowNotice: '所选时间范围内没有匹配的模型，已改为显示近 7 天的匹配列表。',
}

/** Label for a key, with `{name}` placeholders filled from `vars`. */
export function t(lang: UiLang, key: LabelKey, vars: Record<string, string | number> = {}): string {
  const table: Record<LabelKey, string> = lang === 'zh-CN' ? ZH : EN
  return table[key].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`))
}
