// Import subcomponents directly — the brand's index.js re-exports Avatar,
// which transitively requires @lobehub/ui (not installed). OpenAI ships
// only Mono (its logo is monochrome by design); the other three have Color.
import ClaudeColor from '@lobehub/icons/es/Claude/components/Color'
import OpenAIMono from '@lobehub/icons/es/OpenAI/components/Mono'
import DeepSeekColor from '@lobehub/icons/es/DeepSeek/components/Color'
import QwenColor from '@lobehub/icons/es/Qwen/components/Color'
import { Bot, HelpCircle } from 'lucide-react'

interface Props {
  agentId: string
  size?: number
  className?: string
}

/**
 * agentId is the meta.seat_assignment string,
 * e.g. "anthropic:claude-haiku-4-5", "openai:gpt-5.4-mini",
 * "deepseek:deepseek-chat", "qwen:qwen3.6-plus", "rule_based:tag_v1".
 */
export function ProviderBadge({ agentId, size = 18, className }: Props) {
  const [provider] = agentId.split(':')
  switch (provider) {
    case 'anthropic':
      return <ClaudeColor size={size} className={className} />
    case 'openai':
      return <OpenAIMono size={size} className={`text-slate-900 ${className ?? ''}`} />
    case 'deepseek':
      return <DeepSeekColor size={size} className={className} />
    case 'qwen':
      return <QwenColor size={size} className={className} />
    case 'rule_based':
      return <Bot size={size} className={`text-slate-400 ${className ?? ''}`} />
    default:
      return <HelpCircle size={size} className={`text-slate-300 ${className ?? ''}`} />
  }
}
