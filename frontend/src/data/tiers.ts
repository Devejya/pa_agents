import { Tier } from '../types'

export const tiers: Tier[] = [
  {
    level: 1,
    name: 'Essential',
    price: 150,
    description: 'Intelligent assistance for the discerning professional',
    features: [
      'Intelligent & personalized calendar management',
      'Travel arrangements with curated recommendations',
      'Direct booking links & concierge contact',
      'Personalized email prioritization',
    ],
  },
  {
    level: 2,
    name: 'Premier',
    price: 230,
    description: 'An assistant that evolves with you',
    features: [
      'Everything in Essential',
      'Adaptive learning of your preferences',
      'Thoughtful gift suggestions for loved ones',
      'Draft communications on your behalf',
      'Relationship management insights',
    ],
    highlighted: true,
  },
  {
    level: 3,
    name: 'Private',
    price: 400,
    description: 'Complete delegation of your communications',
    features: [
      'Everything in Premier',
      'Voice calls for bookings & reservations',
      'Incoming call management & screening',
      'Real-time transcription & summaries',
      'Priority triage & intelligent routing',
      'Dedicated support line',
    ],
  },
]

