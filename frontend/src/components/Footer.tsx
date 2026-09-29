import { Link } from "react-router-dom"

const LINKS = [
  { to: "/", label: "Home" },
  { to: "/imprint", label: "Imprint" },
  { to: "/privacy", label: "Privacy" },
] as const

export default function Footer() {
  return (
    <footer className="flex h-16 w-full items-center justify-center gap-2 border-t border-[var(--footer-border)] bg-[var(--footer-bg)] sm:gap-4 md:gap-8">
      {LINKS.map((link) => (
        <Link
          key={link.to}
          to={link.to}
          className="px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          {link.label}
        </Link>
      ))}
    </footer>
  )
}
