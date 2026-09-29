import { lazy, Suspense, useEffect } from "react"
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom"
import Footer from "@/components/Footer"
import LoadingState from "@/components/LoadingState"
import HomePage from "@/pages/HomePage"

const ImprintPage = lazy(() => import("@/pages/ImprintPage"))
const PrivacyPage = lazy(() => import("@/pages/PrivacyPage"))
const NewTeamPage = lazy(() => import("@/pages/NewTeamPage"))
const TeamPage = lazy(() => import("@/pages/TeamPage"))
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"))

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <div className="flex min-h-screen flex-col bg-[var(--footer-bg)]">
        <main className="flex-1 bg-background">
          <Suspense fallback={<LoadingState />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/imprint" element={<ImprintPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/new" element={<NewTeamPage />} />
              <Route path="/t/:teamId" element={<TeamPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
