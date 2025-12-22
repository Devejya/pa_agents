import sgMail from '@sendgrid/mail'
import dotenv from 'dotenv'

dotenv.config()

// Initialize SendGrid
const apiKey = process.env.SENDGRID_API_KEY
if (apiKey) {
  sgMail.setApiKey(apiKey)
}

interface TierInfo {
  name: string
  price: number
  description: string
}

// Keep tier data in sync with frontend/src/data/tiers.ts
const tierData: Record<number, TierInfo> = {
  1: { name: 'Guide', price: 150, description: 'Your intelligent assistant for daily essentials' },
  2: { name: 'Partner', price: 230, description: 'An assistant that learns and grows with you' },
  3: { name: 'Chief of Staff', price: 400, description: 'Full delegation of your professional life' },
}

function generateEmailHTML(tierLevel: number): string {
  const tier = tierData[tierLevel] || tierData[1]
  
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to Yennifer</title>
  <!--[if mso]>
  <style type="text/css">
    table { border-collapse: collapse; }
    .fallback-font { font-family: Georgia, serif !important; }
  </style>
  <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #FAFAFA; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FAFAFA;">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width: 600px; width: 100%;">
          
          <!-- Header with Logo -->
          <tr>
            <td align="center" style="padding-bottom: 32px;">
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width: 48px; height: 48px; background: linear-gradient(135deg, #7C3AED, #5B21B6); border-radius: 50%; text-align: center; vertical-align: middle;">
                    <span style="color: #FFFFFF; font-family: Georgia, serif; font-size: 24px; font-weight: normal;">Y</span>
                  </td>
                  <td style="padding-left: 12px;">
                    <span style="font-family: Georgia, serif; font-size: 28px; color: #1F2937; letter-spacing: 0.02em;">Yennifer</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          
          <!-- Main Content Card -->
          <tr>
            <td>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; border-radius: 16px; box-shadow: 0 4px 20px rgba(124, 58, 237, 0.1); border: 1px solid #E5E7EB;">
                <tr>
                  <td style="padding: 48px 40px;">
                    
                    <!-- Welcome Title -->
                    <h1 style="margin: 0 0 24px 0; font-family: Georgia, serif; font-size: 32px; font-weight: normal; color: #1F2937; text-align: center;">
                      Welcome to the Waitlist
                    </h1>
                    
                    <!-- Thank You Message -->
                    <p style="margin: 0 0 32px 0; font-size: 16px; line-height: 1.7; color: #4B5563; text-align: center;">
                      Thank you for joining the Yennifer early access waitlist. We're excited to have you on board.
                    </p>
                    
                    <!-- Selected Plan Box -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: linear-gradient(135deg, #F5F3FF, #FAFAFA); border-radius: 12px; border: 1px solid #E5E7EB; margin-bottom: 24px;">
                      <tr>
                        <td style="padding: 24px;">
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                            <tr>
                              <td>
                                <p style="margin: 0 0 8px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: #7C3AED; font-weight: 500;">
                                  Your Selected Plan
                                </p>
                              </td>
                              <td align="right">
                                <span style="display: inline-block; padding: 4px 10px; background: linear-gradient(135deg, #10B981, #059669); color: #FFFFFF; font-size: 10px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; border-radius: 12px;">Early Bird</span>
                              </td>
                            </tr>
                          </table>
                          <h2 style="margin: 0 0 8px 0; font-family: Georgia, serif; font-size: 24px; font-weight: normal; color: #1F2937;">
                            ${tier.name}
                          </h2>
                          <p style="margin: 0 0 12px 0; font-size: 14px; color: #4B5563;">
                            ${tier.description}
                          </p>
                          <p style="margin: 0; font-size: 28px; color: #1F2937;">
                            <span style="color: #7C3AED; font-size: 18px;">$</span>${tier.price}<span style="font-size: 14px; color: #9CA3AF;">/month</span>
                          </p>
                        </td>
                      </tr>
                    </table>
                    
                    <!-- Early Bird Notice -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #ECFDF5; border-radius: 8px; margin-bottom: 32px;">
                      <tr>
                        <td style="padding: 16px 20px;">
                          <p style="margin: 0; font-size: 14px; color: #065F46; line-height: 1.6;">
                            <strong>🎉 Your early bird price is locked in!</strong><br>
                            You won't be charged until we launch. This exclusive rate is yours forever.
                          </p>
                        </td>
                      </tr>
                    </table>
                    
                    <!-- What's Next -->
                    <h3 style="margin: 0 0 16px 0; font-family: Georgia, serif; font-size: 20px; font-weight: normal; color: #1F2937;">
                      What happens next?
                    </h3>
                    <ul style="margin: 0 0 32px 0; padding-left: 20px; font-size: 15px; line-height: 1.8; color: #4B5563;">
                      <li style="margin-bottom: 8px;">You'll be among the <strong style="color: #7C3AED;">first to know</strong> when we launch</li>
                      <li style="margin-bottom: 8px;">Your <strong style="color: #10B981;">early bird pricing</strong> is locked in forever</li>
                      <li style="margin-bottom: 8px;">Early access members get <strong style="color: #7C3AED;">priority onboarding</strong></li>
                      <li>We'll share exclusive updates on our progress</li>
                    </ul>
                    
                    <!-- Divider -->
                    <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 32px 0;">
                    
                    <!-- Closing -->
                    <p style="margin: 0; font-size: 15px; line-height: 1.7; color: #4B5563; text-align: center;">
                      We're building something special for busy professionals like you. Stay tuned.
                    </p>
                    
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding-top: 32px; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 13px; color: #9CA3AF;">
                This is an automated message. Please do not reply to this email.
              </p>
              <p style="margin: 0; font-size: 13px; color: #9CA3AF;">
                © ${new Date().getFullYear()} Yennifer AI. All rights reserved.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`
}

function generatePlainText(tierLevel: number): string {
  const tier = tierData[tierLevel] || tierData[1]
  
  return `
Welcome to the Yennifer Waitlist!

Thank you for joining our early access waitlist. We're excited to have you on board.

YOUR SELECTED PLAN (Early Bird Pricing)
---------------------------------------
${tier.name}
${tier.description}
$${tier.price}/month

🎉 YOUR EARLY BIRD PRICE IS LOCKED IN!
You won't be charged until we launch. This exclusive rate is yours forever.

WHAT HAPPENS NEXT?
------------------
• You'll be among the first to know when we launch
• Your early bird pricing is locked in forever
• Early access members get priority onboarding
• We'll share exclusive updates on our progress

We're building something special for busy professionals like you. Stay tuned.

---
This is an automated message. Please do not reply to this email.
© ${new Date().getFullYear()} Yennifer AI. All rights reserved.
`
}

export async function sendWelcomeEmail(
  toEmail: string,
  tierLevel: number
): Promise<{ success: boolean; error?: string }> {
  if (!apiKey) {
    console.error('SendGrid API key not configured')
    return { success: false, error: 'Email service not configured' }
  }

  const fromEmail = process.env.SENDGRID_FROM_EMAIL || 'hello@yennifer.ai'
  const fromName = process.env.SENDGRID_FROM_NAME || 'Yennifer'
  const tier = tierData[tierLevel] || tierData[1]

  const msg = {
    to: toEmail,
    from: {
      email: fromEmail,
      name: fromName,
    },
    subject: `Welcome to Yennifer - ${tier.name} Waitlist`,
    text: generatePlainText(tierLevel),
    html: generateEmailHTML(tierLevel),
  }

  try {
    await sgMail.send(msg)
    console.log(`✓ Welcome email sent to ${toEmail} for ${tier.name} plan`)
    return { success: true }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    console.error('✗ Failed to send email:', errorMessage)
    return { success: false, error: errorMessage }
  }
}

