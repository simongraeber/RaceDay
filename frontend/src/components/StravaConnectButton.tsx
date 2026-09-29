import { cn } from "@/lib/utils"

interface Props {
  href: string
  className?: string
}

// TODO: swap for the official "Connect with Strava" asset (required by Strava brand guidelines)
export default function StravaConnectButton({ href, className }: Props) {
  return (
    <a
      href={href}
      className={cn(
        "inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#fc4c02] px-8 text-base font-semibold text-white shadow-md transition hover:brightness-110",
        className,
      )}
    >
      Connect with Strava
    </a>
  )
}
