export type TierLevel = 1 | 2 | 3

export interface Tier {
  level: TierLevel
  name: string
  price: number
  description: string
  features: string[]
  highlighted?: boolean
}

export interface SignupData {
  email: string
  tier: TierLevel
}

export interface SignupResponse {
  success: boolean
  message: string
  eventId?: string
}

