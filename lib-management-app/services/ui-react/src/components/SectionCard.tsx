import type { ComponentProps, ReactNode } from 'react'
import SectionBand from './SectionBand'
import { PaginatedSectionFooter, PaginatedSectionHeader } from './PaginatedSectionControls'

type SectionCardProps = {
  bandTitle?: string
  bandSubtitle?: string
  bandClassName?: string
  cardClassName?: string
  header?: ComponentProps<typeof PaginatedSectionHeader>
  footer?: ComponentProps<typeof PaginatedSectionFooter>
  children: ReactNode
  bodyClassName?: string
}

export default function SectionCard({
  bandTitle,
  bandSubtitle,
  bandClassName,
  cardClassName = 'card overflow-hidden',
  header,
  footer,
  children,
  bodyClassName,
}: SectionCardProps) {
  return (
    <>
      {bandTitle && bandSubtitle && (
        <SectionBand
          title={bandTitle}
          subtitle={bandSubtitle}
          className={bandClassName}
        />
      )}
      <div className={cardClassName}>
        {header && <PaginatedSectionHeader {...header} />}
        {bodyClassName ? <div className={bodyClassName}>{children}</div> : children}
        {footer && <PaginatedSectionFooter {...footer} />}
      </div>
    </>
  )
}
