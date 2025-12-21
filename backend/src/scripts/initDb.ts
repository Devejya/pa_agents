import { pool, testConnection } from '../config/database.js'

const CREATE_SIGNUPS_TABLE = `
CREATE TABLE IF NOT EXISTS signups (
  event_id UUID PRIMARY KEY,
  signup_created_at_est TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/New_York'),
  user_email_id VARCHAR(255) NOT NULL,
  user_tier INTEGER NOT NULL CHECK (user_tier IN (1, 2, 3)),
  CONSTRAINT unique_email UNIQUE (user_email_id)
);
`

const CREATE_INDEX = `
CREATE INDEX IF NOT EXISTS idx_signups_created_at ON signups (signup_created_at_est DESC);
`

async function initializeDatabase() {
  console.log('🚀 Initializing database...\n')
  
  const connected = await testConnection()
  if (!connected) {
    console.error('Cannot proceed without database connection')
    process.exit(1)
  }

  try {
    console.log('\n📋 Creating signups table...')
    await pool.query(CREATE_SIGNUPS_TABLE)
    console.log('✓ Signups table created/verified')

    console.log('\n📋 Creating indexes...')
    await pool.query(CREATE_INDEX)
    console.log('✓ Indexes created/verified')

    console.log('\n✅ Database initialization complete!')
  } catch (error) {
    console.error('Error initializing database:', error)
    process.exit(1)
  } finally {
    await pool.end()
  }
}

initializeDatabase()

