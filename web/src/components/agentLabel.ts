/**
 * OpenRouter is a multi-vendor gateway, so an agentId like
 * "openrouter:google/gemini-3.1-pro-preview" needs to be re-keyed by
 * the *underlying* vendor before the icon / label switches can match
 * (otherwise the UI shows a generic "?" badge and the literal model
 * id in place of "Gemini 3.1 pro preview"). Returns a synthetic
 * agentId in the canonical "vendor:model" shape; pass-through for
 * non-openrouter ids. Used by both ProviderBadge and shortAgentLabel.
 */
export function normalizeAgentId(agentId: string): string {
  const [provider, ...rest] = agentId.split(':')
  if (provider !== 'openrouter') return agentId
  const model = rest.join(':')
  const slash = model.indexOf('/')
  if (slash < 0) return agentId
  const vendor = model.slice(0, slash)
  const inner = model.slice(slash + 1)
  // OpenRouter vendor prefixes → our internal provider tags.
  // Add new mappings here when we route a new vendor through OR.
  const vendorToProvider: Record<string, string> = {
    google: 'gemini',
    anthropic: 'anthropic',
    openai: 'openai',
    deepseek: 'deepseek',
    qwen: 'qwen',
    moonshotai: 'kimi',
    'x-ai': 'grok',
  }
  const mapped = vendorToProvider[vendor]
  if (!mapped) return agentId
  return `${mapped}:${inner}`
}

/**
 * Short, header-friendly label for an agentId from
 * `meta.seat_assignment` (e.g. "anthropic:claude-haiku-4-5"
 * → "Haiku 4.5").
 *
 * Pure function; lives in its own file so ProviderBadge.tsx can
 * stay 100% component exports (react-refresh requirement).
 */
export function shortAgentLabel(rawAgentId: string): string {
  const agentId = normalizeAgentId(rawAgentId)
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
