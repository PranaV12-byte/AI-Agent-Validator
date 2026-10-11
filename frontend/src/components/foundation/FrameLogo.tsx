import type { SVGProps } from "react"

type FrameLogoProps = {
  size?: 24 | 28 | 32 | 64
  showWordmark?: boolean
  className?: string
  markProps?: SVGProps<SVGSVGElement>
}

export function FrameLogo({ size = 28, showWordmark = true, className = "", markProps }: FrameLogoProps) {
  const mark = (
    <svg
      aria-label={showWordmark ? undefined : "SafeBot Frame mark"}
      aria-hidden={showWordmark ? true : undefined}
      className={"fd-logo-mark " + (markProps?.className ?? "")}
      data-internal-gap="2"
      focusable="false"
      height={size}
      role={showWordmark ? undefined : "img"}
      viewBox="0 0 32 32"
      width={size}
      {...markProps}
    >
      <path d="M4 4h18v4H8v14H4V4Z" fill="#365DF0" />
      <path d="M28 28H10v-4h14V10h4v18Z" fill="#365DF0" />
    </svg>
  )

  if (!showWordmark) return mark

  return (
    <span className={"fd-logo-lockup " + className}>
      {mark}
      <span className="fd-brand__wordmark">SafeBot</span>
    </span>
  )
}
