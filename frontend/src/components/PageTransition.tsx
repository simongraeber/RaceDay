import type { ReactNode } from "react"
import { motion } from "framer-motion"
import { pageVariants } from "@/lib/animations"

export default function PageTransition({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div className={className} variants={pageVariants} initial="hidden" animate="show">
      {children}
    </motion.div>
  )
}
