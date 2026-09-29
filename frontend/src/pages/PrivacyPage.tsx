import { Link } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import PageTransition from "@/components/PageTransition"

const EMAIL = "80-read-crewel@icloud.com"

export default function PrivacyPage() {
  return (
    <PageTransition className="mx-auto max-w-3xl px-4 py-8 text-center">
      <h1 className="mb-4 text-3xl font-bold">Privacy</h1>

      <div className="legal-content">
        <h2>1. General</h2>
        <p>
          This policy explains how RaceDay processes personal data in accordance with the EU General
          Data Protection Regulation (GDPR).
        </p>

        <h2>2. Controller</h2>
        <p>
          Simon Graeber
          <br />
          Mitthenheimer Str. 6, 85764 Oberschleißheim, Germany
          <br />
          E-Mail: {EMAIL}
        </p>

        <h2>3. Visitors</h2>
        <p>
          You can view the landing page and team pages without an account. We do not use tracking,
          analytics, or advertising cookies. Our web server processes technically necessary data such
          as your IP address to deliver the page.
        </p>

        <h2>4. Strava connection</h2>
        <p>
          When you join or create a team, you log in with Strava (OAuth). With your permission we
          receive and store:
        </p>
        <ul>
          <li>Your Strava athlete ID, first name, last name, and profile picture URL</li>
          <li>
            Your runs from the last 12 months that are visible to Everyone or Followers: date,
            distance, duration, elevation, and a simplified route
          </li>
          <li>Access tokens, stored encrypted, so we can receive new runs automatically</li>
        </ul>
        <p>
          We never read activities set to "Only Me" or your Strava privacy zones. We additionally
          remove the first and last 200 metres of every route before storing it.
        </p>

        <h2>5. Who can see your data</h2>
        <p>
          Your first name, last initial, profile picture, run statistics, and routes are{" "}
          <strong>visible to anyone who has the link to your team</strong>. Team links are not listed
          or searchable. You can hide yourself from a team at any time.
        </p>

        <h2>6. Cookies</h2>
        <p>
          We use two strictly necessary cookies: a short-lived one to secure the Strava login, and a
          session cookie that keeps you logged in for up to 30 days.
        </p>

        <h2>7. Legal basis and retention</h2>
        <p>
          Processing is based on your consent (Art. 6(1)(a) GDPR), given when you connect Strava. We
          keep your data until you delete your account or revoke RaceDay's access in your Strava
          settings, after which it is deleted.
        </p>

        <h2>8. Your rights</h2>
        <p>
          You have the right to access, rectify, or delete your data, to restrict or object to its
          processing, to data portability, and to withdraw consent at any time. You also have the
          right to lodge a complaint with a supervisory authority. Contact us at {EMAIL}.
        </p>

        <h2>9. Changes</h2>
        <p>We may update this policy. The current version is always published here.</p>
      </div>

      <Button variant="outline" asChild>
        <Link to="/">
          <ArrowLeft />
          Back to Home
        </Link>
      </Button>
    </PageTransition>
  )
}
