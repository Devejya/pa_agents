import { useState, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useSignup } from '../hooks/useSignup'
import { TierLevel, Tier } from '../types'
import { tiers } from '../data/tiers'
import styles from './SignupForm.module.css'

interface SignupFormProps {
  selectedTier: TierLevel
}

export function SignupForm({ selectedTier }: SignupFormProps) {
  const [email, setEmail] = useState('')
  const { isLoading, isSuccess, error, submit } = useSignup()
  
  const tier: Tier | undefined = tiers.find(t => t.level === selectedTier)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (email.trim()) {
      await submit(email.trim(), selectedTier)
    }
  }

  if (isSuccess) {
    return (
      <div className={styles.successContainer}>
        <div className={styles.successIcon}>✓</div>
        <h2 className={styles.successTitle}>Welcome to Yennifer</h2>
        <p className={styles.successMessage}>
          You're on the waitlist for our <strong>{tier?.name}</strong> plan.
          <br />
          We'll be in touch soon.
        </p>
        <Link to="/" className={styles.backLink}>
          Return Home
        </Link>
      </div>
    )
  }

  return (
    <div className={styles.formContainer}>
      <div className={styles.tierInfo}>
        <span className={styles.tierLabel}>Selected Plan</span>
        <span className={styles.tierName}>{tier?.name}</span>
        <span className={styles.tierPrice}>${tier?.price}/month</span>
      </div>

      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.inputGroup}>
          <label htmlFor="email" className={styles.label}>
            Email Address
          </label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            disabled={isLoading}
            className={styles.input}
            autoComplete="email"
          />
        </div>

        {error && (
          <p className={styles.error}>{error}</p>
        )}

        <button 
          type="submit" 
          disabled={isLoading || !email.trim()}
          className={styles.submitButton}
        >
          {isLoading ? (
            <span className={styles.loadingSpinner}>
              <span className={styles.spinnerDot}></span>
              <span className={styles.spinnerDot}></span>
              <span className={styles.spinnerDot}></span>
            </span>
          ) : (
            'Join the Waitlist'
          )}
        </button>
      </form>

      <p className={styles.disclaimer}>
        By joining, you agree to receive updates about Yennifer.
        <br />
        Your information is kept strictly confidential.
      </p>

      <Link to="/" className={styles.changeLink}>
        ← Choose a different plan
      </Link>
    </div>
  )
}

