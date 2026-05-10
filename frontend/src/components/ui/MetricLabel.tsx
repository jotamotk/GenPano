import React from 'react'
import InfoTooltip from './InfoTooltip'

export interface MetricLabelProps {
  children: React.ReactNode
  helpText?: React.ReactNode
  label?: string
  placement?: 'top' | 'bottom'
  className?: string
}

export default function MetricLabel({
  children,
  helpText,
  label = 'info',
  placement = 'top',
  className = '',
}: MetricLabelProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 align-middle ${className}`.trim()}>
      <span>{children}</span>
      <InfoTooltip text={helpText} label={label} placement={placement} />
    </span>
  )
}
