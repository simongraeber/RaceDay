import { motion } from "framer-motion"
import { Link } from "react-router-dom"
import { ArrowLeft, Mail, MapPin, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import PageTransition from "@/components/PageTransition"
import { fadeUp, popIn, staggerContainer } from "@/lib/animations"

export default function ImprintPage() {
  return (
    <PageTransition className="mx-auto max-w-3xl px-4 py-8 text-center">
      <h1 className="mb-6 text-3xl font-bold">Imprint</h1>

      <motion.div variants={staggerContainer} initial="hidden" animate="show">
        <motion.div variants={popIn}>
          <Card className="relative mb-8 overflow-hidden">
            <div className="absolute left-0 top-0 size-40 rounded-full bg-gradient-to-br from-[var(--glow-from)] to-[var(--glow-to)] blur-[40px]" />
            <CardContent className="relative z-10 flex flex-col items-center gap-6 p-8 md:flex-row">
              <img src="/logo.svg" alt="RaceDay" className="size-24 shrink-0 rounded-xl" />
              <div className="flex min-w-0 flex-col gap-4 text-left">
                <div className="flex items-center gap-2">
                  <User className="size-5 text-primary" />
                  <h2 className="text-xl font-bold">Simon Graeber</h2>
                </div>
                <div className="h-0.5 w-16 bg-primary" />
                <div className="flex flex-col gap-3 text-sm">
                  <div className="flex items-start gap-2">
                    <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div>
                      <p>Mitthenheimer Str. 6</p>
                      <p>85764 Oberschleißheim</p>
                      <p>Germany</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <a href="mailto:80-read-crewel@icloud.com" className="hover:underline">
                      80-read-crewel@icloud.com
                    </a>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={fadeUp}>
          <Button variant="outline" asChild>
            <Link to="/">
              <ArrowLeft />
              Back to Home
            </Link>
          </Button>
        </motion.div>
      </motion.div>
    </PageTransition>
  )
}
