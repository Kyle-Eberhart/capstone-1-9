# SendGrid Email Setup (One-Time Admin Setup)

**No user configuration needed!** Once set up, any user can send emails to any email address.

## Why SendGrid?

- ✅ Works with **any email provider** (Gmail, Outlook, Yahoo, etc.)
- ✅ **No user setup required** - works automatically for all users
- ✅ Free tier: **100 emails/day for 60 days**
- ✅ Simple API key setup (one-time admin configuration)
- ✅ Professional email delivery

## One-Time Setup (Admin Only)

### Step 1: Create SendGrid Account
1. Go to [SendGrid Free Account](https://sendgrid.com/free/)
2. Sign up for a free account (no credit card required)
3. Verify your email address

### Step 2: Create API Key
1. Log in to SendGrid dashboard
2. Go to **Settings** → **API Keys**
3. Click **Create API Key**
4. Name it "Exam Grader" or similar
5. Select **Full Access** or **Restricted Access** with "Mail Send" permission
6. Click **Create & View**
7. **Copy the API key immediately** (you won't see it again!)

### Step 3: Add to .env File
Add this line to your `.env` file:

```env
# Email Configuration (SendGrid API)
SENDGRID_API_KEY=SG.your_api_key_here
EMAIL_FROM_ADDRESS=noreply@examgrader.com
EMAIL_FROM_NAME=AI Exam Grader
```

**Important:**
- Replace `SG.your_api_key_here` with your actual SendGrid API key
- The `EMAIL_FROM_ADDRESS` can be any email (doesn't need to exist)
- The `EMAIL_FROM_NAME` is what recipients will see as the sender name

### Step 4: Install SendGrid Library
```bash
pip install sendgrid
```

Or if using requirements.txt:
```bash
pip install -r requirements.txt
```

### Step 5: Restart Application
Restart your FastAPI server for changes to take effect.

## How It Works

1. **Admin sets up SendGrid API key once** (this setup)
2. **Any user** can dispute a grade
3. **System automatically sends email** to the instructor's email address
4. **Works with any email provider** - Gmail, Outlook, Yahoo, etc.
5. **No user configuration needed** - completely automatic!

## Free Tier Limits

- **100 emails per day** for 60 days (free trial)
- After 60 days: Pay-as-you-go pricing starts at $19.95/month
- Perfect for development and small deployments

## Troubleshooting

### "Email not configured - SendGrid API key missing"
- Check that `SENDGRID_API_KEY` is in your `.env` file
- Make sure there are no extra spaces or quotes around the key
- Restart the application after adding the key

### "SendGrid library not installed"
- Run: `pip install sendgrid`
- Or: `pip install -r requirements.txt`

### Email not sending
- Check SendGrid dashboard for delivery status
- Verify API key has "Mail Send" permissions
- Check application logs for specific error messages

## Alternative: Other Email Services

If you prefer a different service:

- **Mailgun**: Free tier (5,000 emails/month)
- **AWS SES**: Pay-as-you-go (very cheap)
- **Postmark**: Developer-friendly pricing

These would require code changes to implement.
