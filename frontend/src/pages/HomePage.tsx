import { useEffect } from 'react'
import { usePostHog } from 'posthog-js/react'
import { Header } from '../components/Header'
import { Footer } from '../components/Footer'
import { TierCard } from '../components/TierCard'
import { tiers } from '../data/tiers'
import styles from './HomePage.module.css'

export function HomePage() {
  const posthog = usePostHog()

  useEffect(() => {
    posthog?.capture('$pageview', { page: 'home' })
  }, [posthog])

  return (
    <div className={styles.page}>
      <Header />
      
      <main className={styles.main}>
        {/* Hero Section */}
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <h1 className={styles.heroTitle}>
              Your AI
              <span className={styles.heroAccent}> Executive Assistant</span>
            </h1>
            <p className={styles.heroSubtitle}>
              Discrete. Intelligent. Available 24/7.
            </p>
            <p className={styles.heroDescription}>
              Reclaim your time with an AI assistant that manages your calendar, 
              arranges travel, handles communications, and anticipates your needs—
              available around the clock, so you can focus on what matters most.
            </p>
          </div>
          <div className={styles.heroGlow}></div>
        </section>

        {/* Pricing Section */}
        <section className={styles.pricing}>
          <div className={styles.pricingHeader}>
            <h2 className={styles.pricingTitle}>Choose Your Experience</h2>
            <p className={styles.pricingSubtitle}>
              Select the level of assistance that fits your lifestyle
            </p>
          </div>
          
          <div className={styles.tiersGrid}>
            {tiers.map((tier, index) => (
              <TierCard 
                key={tier.level} 
                tier={tier} 
                animationDelay={index * 100 + 200}
              />
            ))}
          </div>
        </section>

        {/* Trust Section */}
        <section className={styles.trust}>
          <div className={styles.trustContent}>
            <h3 className={styles.trustTitle}>Built for Privacy</h3>
            <p className={styles.trustText}>
              Your information is encrypted, secure, and never shared. 
              We understand that discretion is not a feature—it's a requirement.
            </p>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

