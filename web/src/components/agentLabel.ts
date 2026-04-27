/**
 * Short, header-friendly label for an agentId from
 * `meta.seat_assignment` (e.g. "anthropic:claude-haiku-4-5"
 * → "Haiku 4.5").
 *
 * Pure function; lives in its own file so ProviderBadge.tsx can
 * stay 100% component exports (react-refresh requirement).
 */
export function shortAgentLabel(agentId: string): string {
  const [provider, ...rest] = agentId.split(':')
  const model = rest.join(':')
  switch (provider) {
    case 'anthropic': {
      // "claude-haiku-4-5" → "Haiku 4.5"; "claude-sonnet-4-6" → "Sonnet 4.6"
      if (model.startsWith('claude-')) {
        const parts = model.replace('claude-', '').split('-')
        const family = parts[0].charAt(0).toUpperCase() + parts[0].slice(1)
        const version = parts.slice(1).join('.')
        return version ? `${family} ${version}` : family
      }
      return model || 'Claude'
    }
    case 'openai': {
      // "gpt-5.4-mini" → "GPT-5.4 mini"; "gpt-4o" → "GPT-4O"
      return model.toUpperCase().replace('-', ' ').replace(/MINI/i, 'mini')
    }
    case 'deepseek': {
      // "deepseek-chat"/"deepseek-reasoner" → "DeepSeek"
      // "deepseek-v4-flash" → "DeepSeek v4 flash"
      if (model === 'deepseek-chat' || model === 'deepseek-reasoner') return 'DeepSeek'
      const ds = model.replace(/^deepseek-/, '').replace(/-/g, ' ')
      return `DeepSeek ${ds}`
    }
    case 'qwen': {
      // "qwen3.6-plus" → "Qwen 3.6 plus"
      return model.replace(/^qwen/, 'Qwen ').replace(/-/g, ' ')
    }
    case 'rule_based':
      return 'Rule-based'
    default:
      return agentId
  }
}
