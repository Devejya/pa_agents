import { useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { usePostHog } from 'posthog-js/react'
import { Header } from '../components/Header'
import { Footer } from '../components/Footer'
import { SignupForm } from '../components/SignupForm'
import { TierLevel } from '../types'
import styles from './CheckoutPage.module.css'

const VALID_TIERS: TierLevel[] = [1, 2, 3]

export function CheckoutPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const posthog = usePostHog()
  
  const tierParam = searchParams.get('tier')
  const selectedTier = tierParam ? parseInt(tierParam, 10) as TierLevel : null

  useEffect(() => {
    posthog?.capture('$pageview', { 
      page: 'checkout',
      tier: selectedTier,
    })
  }, [posthog, selectedTier])

  // Redirect to home if no valid tier selected
  useEffect(() => {
    if (!selectedTier || !VALID_TIERS.includes(selectedTier)) {
      navigate('/')
    }
  }, [selectedTier, navigate])

  if (!selectedTier || !VALID_TIERS.includes(selectedTier)) {
    return null
  }

  return (
    <div className={styles.page}>
      <Header />
      
      <main className={styles.main}>
        <div className={styles.content}>
          <div className={styles.header}>
            <h1 className={styles.title}>Join the Waitlist</h1>
            <p className={styles.subtitle}>
              Be among the first to experience Yennifer
            </p>
          </div>
          
          <SignupForm selectedTier={selectedTier} />
        </div>
      </main>

      <Footer />
    </div>
  )
}

