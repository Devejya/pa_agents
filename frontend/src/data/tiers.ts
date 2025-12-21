import { Tier } from '../types'

export const tiers: Tier[] = [
  {
    level: 1,
    name: 'Guide',
    price: 150,
    description: 'Your intelligent assistant for daily essentials',
    features: [
      'Intelligent & personalized calendar management',
      'Travel arrangements with curated recommendations',
      'Direct booking links & concierge contact',
      'Personalized email prioritization',
    ],
  },
  {
    level: 2,
    name: 'Partner',
    price: 230,
    description: 'An assistant that learns and grows with you',
    features: [
      'Everything in Guide',
      'Adaptive learning of your preferences',
      'Thoughtful gift suggestions for loved ones',
      'Draft communications on your behalf',
      'Relationship management insights',
    ],
    highlighted: true,
  },
  {
    level: 3,
    name: 'Chief of Staff',
    price: 400,
    description: 'Full delegation of your professional life',
    features: [
      'Everything in Partner',
      'Voice calls for bookings & reservations',
      'Incoming call management & screening',
      'Real-time transcription & summaries',
      'Priority triage & intelligent routing',
      'Dedicated support line',
    ],
  },
]

