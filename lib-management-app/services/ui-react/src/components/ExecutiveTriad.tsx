type TriadTone = 'neutral' | 'warning' | 'critical' | 'positive'

interface ExecutiveTriadProps {
  impact: string
  owner: string
  nextAction: string
  tone?: TriadTone
}

const toneClassMap: Record<TriadTone, string> = {
  neutral: 'executive-triad-neutral',
  warning: 'executive-triad-warning',
  critical: 'executive-triad-critical',
  positive: 'executive-triad-positive',
}

export default function ExecutiveTriad({ impact, owner, nextAction, tone = 'neutral' }: ExecutiveTriadProps) {
  return (
    <div className={`executive-triad ${toneClassMap[tone]}`}>
      <div className="executive-triad-item">
        <p className="executive-triad-label">Business Impact</p>
        <p className="executive-triad-value">{impact}</p>
      </div>
      <div className="executive-triad-item">
        <p className="executive-triad-label">Owner</p>
        <p className="executive-triad-value">{owner}</p>
      </div>
      <div className="executive-triad-item">
        <p className="executive-triad-label">Next Action</p>
        <p className="executive-triad-value">{nextAction}</p>
      </div>
    </div>
  )
}