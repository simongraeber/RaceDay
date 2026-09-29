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
            Your runs from the last 12 months — including those you share only with followers or keep
            private on Strava: date, distance, duration, elevation, kilometre splits, best efforts and
            kudos count. GPS tracks are stored for runs shared with followers or everyone; tracks for
            runs set to Only You are never stored.
          </li>
          <li>Access tokens, stored encrypted, so we can receive new runs automatically</li>
        </ul>
        <p>
          Private and followers-only runs count towards your team's statistics and are shown there like
          any other run, so only connect if you are comfortable with that. We never store heart-rate data,
          and we remove the first and last 400 metres of every route and GPS track before storing it.
        </p>

        <h2>5. Optional AI avatar</h2>
        <p>
          If you choose to make a runner avatar, we send the photo you upload and your optional
          description to OpenAI for image generation, together with a fixed character style reference.
          RaceDay does not store your original photo. We store the generated avatar until you remove
          it or delete your account. OpenAI processes your photo under its own privacy terms; do not
          upload someone else's photo without their permission.
        </p>
        <p>
          If you have an avatar, we also send it to OpenAI to draw a few playful variations of your
          character for the highlight cards and to draw it as separate body parts, which lets your
          character run across the training map. Team-wide highlight images combine visible members'
          generated avatars; cards featuring one runner use only that runner's avatar. Highlight images
          are regenerated when the visible roster, avatar, or featured runner changes. No training data,
          names or original photos are sent with the image request.
        </p>

        <h2>6. AI coach comments</h2>
        <p>
          Team pages show short, humorous comments about recent training. To write them, we send
          OpenAI aggregated training numbers (for example weekly distance, run count and predicted
          finish time) under anonymous labels such as “R1”. Names, photos, routes and Strava IDs are
          not sent.
        </p>
        <p>
          Team members can also ask the “Ask AI” analyst questions about the team's runs. The question
          (with runner names replaced by labels like “R1”), the table layout and the query results are
          sent to OpenAI. The AI only reads a temporary, read-only copy of the visible members' run
          statistics (dates, distances, times, elevation, kudos, best efforts and splits); it never sees
          names, photos, GPS routes or Strava accounts and cannot change any data. Questions are not stored.
        </p>

        <h2>7. Who can see your data</h2>
        <p>
          Your first name, last initial, profile picture or generated avatar, run statistics, and routes are{" "}
          <strong>visible to anyone who has the link to your team</strong>. Team links are not listed
          or searchable. You can hide yourself from a team at any time.
        </p>

        <h2>8. Cookies</h2>
        <p>
          We use two strictly necessary cookies: a short-lived one to secure the Strava login, and a
          session cookie that keeps you logged in for up to 30 days.
        </p>

        <h2>9. Legal basis and retention</h2>
        <p>
          Processing is based on your consent (Art. 6(1)(a) GDPR), given when you connect Strava. We
          keep your data until you delete your account or revoke RaceDay's access in your Strava
          settings, after which it is deleted.
        </p>

        <h2>10. Your rights</h2>
        <p>
          You have the right to access, rectify, or delete your data, to restrict or object to its
          processing, to data portability, and to withdraw consent at any time. You also have the
          right to lodge a complaint with a supervisory authority. Contact us at {EMAIL}.
        </p>

        <h2>11. Changes</h2>
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
