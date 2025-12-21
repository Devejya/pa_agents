import { useNavigate } from 'react-router-dom'
import { usePostHog } from 'posthog-js/react'
import { Tier } from '../types'
import styles from './TierCard.module.css'

interface TierCardProps {
  tier: Tier
  animationDelay?: number
}

export function TierCard({ tier, animationDelay = 0 }: TierCardProps) {
  const navigate = useNavigate()
  const posthog = usePostHog()

  const handleSelect = () => {
    // Track tier selection
    posthog?.capture('tier_selected', {
      tier: tier.level,
      tier_name: tier.name,
      tier_price: tier.price,
    })
    
    navigate(`/checkout?tier=${tier.level}`)
  }

  return (
    <div 
      className={`${styles.card} ${tier.highlighted ? styles.highlighted : ''}`}
      style={{ animationDelay: `${animationDelay}ms` }}
    >
      {tier.highlighted && (
        <div className={styles.badge}>Most Popular</div>
      )}
      
      <div className={styles.header}>
        <h3 className={styles.name}>{tier.name}</h3>
        <p className={styles.description}>{tier.description}</p>
      </div>
      
      <div className={styles.pricing}>
        <span className={styles.currency}>$</span>
        <span className={styles.amount}>{tier.price}</span>
        <span className={styles.period}>/month</span>
      </div>
      
      <ul className={styles.features}>
        {tier.features.map((feature, index) => (
          <li key={index} className={styles.feature}>
            <span className={styles.checkIcon}>✓</span>
            {feature}
          </li>
        ))}
      </ul>
      
      <button 
        className={`${styles.button} ${tier.highlighted ? styles.buttonHighlighted : ''}`}
        onClick={handleSelect}
      >
        Join Waitlist
      </button>
    </div>
  )
}

