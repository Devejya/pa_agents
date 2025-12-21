import express from 'express'
import cors from 'cors'
import dotenv from 'dotenv'
import path from 'path'
import { fileURLToPath } from 'url'
import { testConnection } from './config/database.js'
import signupRouter from './routes/signup.js'

dotenv.config()

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()
const PORT = parseInt(process.env.PORT || '3001', 10)

// CORS configuration
const corsOrigins = process.env.CORS_ORIGINS?.split(',') || [
  'http://localhost:5173',
  'https://yennifer.ai',
  'https://www.yennifer.ai',
]

app.use(cors({
  origin: corsOrigins,
  methods: ['GET', 'POST'],
  allowedHeaders: ['Content-Type'],
}))

// Middleware
app.use(express.json())

// API Routes
app.use('/api/signup', signupRouter)

// Health check - uses cached DB status to avoid exhausting connection pool
app.get('/api/health', async (_req, res) => {
  const dbConnected = await testConnection(true) // useCache = true
  res.json({
    status: dbConnected ? 'healthy' : 'degraded',
    timestamp: new Date().toISOString(),
    database: dbConnected ? 'connected' : 'disconnected',
  })
})

// Serve static files in production
if (process.env.NODE_ENV === 'production') {
  const staticPath = path.join(__dirname, '../../frontend/dist')
  app.use(express.static(staticPath))
  
  // Handle SPA routing
  app.get('*', (_req, res) => {
    res.sendFile(path.join(staticPath, 'index.html'))
  })
}

// Start server
async function start() {
  console.log('🚀 Starting Yennifer API...\n')
  
  // Test database connection
  await testConnection()
  
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`\n✓ Server running on port ${PORT}`)
    console.log(`  Environment: ${process.env.NODE_ENV || 'development'}`)
    console.log(`  CORS origins: ${corsOrigins.join(', ')}`)
  })
}

start().catch(console.error)

