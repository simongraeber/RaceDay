import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import PageTransition from "@/components/PageTransition"

export default function NotFoundPage() {
  return (
    <PageTransition className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="gradient-text text-6xl font-extrabold">404</h1>
      <p className="text-muted-foreground">Wrong turn. This page doesn't exist — or the link is incomplete.</p>
      <Button variant="outline" asChild>
        <Link to="/">Back to Home</Link>
      </Button>
    </PageTransition>
  )
}
