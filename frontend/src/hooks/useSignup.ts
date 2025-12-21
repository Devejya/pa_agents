import { useState } from 'react'
import { usePostHog } from 'posthog-js/react'
import { submitSignup } from '../services/api'
import { TierLevel, SignupResponse } from '../types'
import { tiers } from '../data/tiers'

interface UseSignupReturn {
  isLoading: boolean
  isSuccess: boolean
  error: string | null
  submit: (email: string, tier: TierLevel) => Promise<void>
  reset: () => void
}

export function useSignup(): UseSignupReturn {
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const posthog = usePostHog()

  const submit = async (email: string, tier: TierLevel) => {
    setIsLoading(true)
    setError(null)

    try {
      const response: SignupResponse = await submitSignup({ email, tier })
      
      if (response.success) {
        setIsSuccess(true)
        
        // Track successful signup with PostHog
        const tierData = tiers.find(t => t.level === tier)
        posthog?.capture('waitlist_signup', {
          tier: tier,
          tier_name: tierData?.name ?? 'Unknown',
        })
      } else {
        throw new Error(response.message || 'Signup failed')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred'
      setError(message)
      
      // Track failed signup attempt
      posthog?.capture('waitlist_signup_error', {
        tier: tier,
        error: message,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const reset = () => {
    setIsLoading(false)
    setIsSuccess(false)
    setError(null)
  }

  return { isLoading, isSuccess, error, submit, reset }
}

