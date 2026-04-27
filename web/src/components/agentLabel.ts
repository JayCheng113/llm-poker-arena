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
    case 'kimi': {
      // "kimi-k2.6" → "Kimi K2.6"; strip prefix, then upper-case the
      // leading letter of the remainder (Moonshot naming: K1/K2/K2.5/K2.6).
      const rest = model.replace(/^kimi-?/, '').replace(/-/g, ' ')
      const head = rest.charAt(0).toUpperCase() + rest.slice(1)
      return `Kimi ${head}`.trim()
    }
    case 'grok': {
      // "grok-2" / "grok-3-mini" → "Grok 2" / "Grok 3 mini"
      return model.replace(/^grok-?/, 'Grok ').replace(/-/g, ' ').trim()
    }
    case 'gemini': {
      // "gemini-2.0-flash" → "Gemini 2.0 flash"
      return model.replace(/^gemini-?/, 'Gemini ').replace(/-/g, ' ').trim()
    }
    case 'rule_based':
      return 'Rule-based'
    default:
      return agentId
  }
}
