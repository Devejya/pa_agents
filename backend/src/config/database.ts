import pg from 'pg'
import dotenv from 'dotenv'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

dotenv.config({ path: path.resolve(__dirname, '../../.env') })

const { Pool } = pg

export const pool = new Pool({
  host: process.env.DB_HOST,
  port: parseInt(process.env.DB_PORT || '5432', 10),
  database: process.env.DB_NAME || 'postgres',
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  ssl: {
    rejectUnauthorized: false, // Required for RDS
  },
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
})

pool.on('error', (err) => {
  console.error('Unexpected error on idle database client', err)
})

// Cache for health check to avoid exhausting connection pool
let healthCache: { status: boolean; timestamp: number } | null = null
const HEALTH_CACHE_TTL_MS = 30000 // 30 seconds

export async function testConnection(useCache = false): Promise<boolean> {
  // Return cached status if valid and caching is enabled
  if (useCache && healthCache && Date.now() - healthCache.timestamp < HEALTH_CACHE_TTL_MS) {
    return healthCache.status
  }

  try {
    // Use pool.query() instead of pool.connect() - it handles connection
    // acquisition/release internally and is more efficient for simple queries
    await pool.query('SELECT 1')
    
    if (!useCache) {
      console.log('✓ Database connection successful')
    }
    
    // Only update cache when caching is enabled
    if (useCache) {
      healthCache = { status: true, timestamp: Date.now() }
    }
    return true
  } catch (error) {
    if (!useCache) {
      console.error('✗ Database connection failed:', error)
    }
    
    // Only update cache when caching is enabled
    if (useCache) {
      healthCache = { status: false, timestamp: Date.now() }
    }
    return false
  }
}

