import { Router, Request, Response } from 'express'
import { v4 as uuidv4 } from 'uuid'
import { pool } from '../config/database.js'

const router = Router()

interface SignupBody {
  email: string
  tier: number
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const VALID_TIERS = [1, 2, 3]

router.post('/', async (req: Request<object, object, SignupBody>, res: Response) => {
  try {
    const { email, tier } = req.body

    // Validation
    if (!email || typeof email !== 'string') {
      res.status(400).json({ 
        success: false, 
        message: 'Email is required' 
      })
      return
    }

    const normalizedEmail = email.trim().toLowerCase()

    if (!EMAIL_REGEX.test(normalizedEmail)) {
      res.status(400).json({ 
        success: false, 
        message: 'Please provide a valid email address' 
      })
      return
    }

    if (!tier || !VALID_TIERS.includes(tier)) {
      res.status(400).json({ 
        success: false, 
        message: 'Please select a valid plan' 
      })
      return
    }

    const eventId = uuidv4()

    // Insert into database
    const query = `
      INSERT INTO signups (event_id, user_email_id, user_tier)
      VALUES ($1, $2, $3)
      ON CONFLICT (user_email_id) 
      DO UPDATE SET 
        user_tier = EXCLUDED.user_tier,
        signup_created_at_est = NOW() AT TIME ZONE 'America/New_York'
      RETURNING event_id
    `

    const result = await pool.query(query, [eventId, normalizedEmail, tier])
    const returnedEventId = result.rows[0]?.event_id || eventId

    console.log(`✓ Signup recorded: ${normalizedEmail} (Tier ${tier})`)

    res.status(201).json({
      success: true,
      message: 'Successfully joined the waitlist',
      eventId: returnedEventId,
    })
  } catch (error) {
    console.error('Signup error:', error)
    res.status(500).json({
      success: false,
      message: 'An error occurred. Please try again.',
    })
  }
})

export default router

