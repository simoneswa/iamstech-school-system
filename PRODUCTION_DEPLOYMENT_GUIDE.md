# IAMSTECH Production Deployment & Validation Guide

**Last Updated:** May 9, 2026  
**Environment:** Railway Production  
**Status:** Ready for Final Validation

---

## 1. RAILWAY ENVIRONMENT VARIABLES SETUP

### Critical Production Configuration

You **MUST** set these variables in your Railway project dashboard:

```
IAMSTECH_BASE_URL=https://your-railway-public-domain.railway.app
MAIL_USERNAME=your-smtp-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=noreply@iamstech.edu.lr
SECRET_KEY=your-secure-random-key-here
DEV_MODE=false
IAMSTECH_REG_SAFE_MODE=false
```

### How to Set Variables in Railway

1. Go to your Railway project dashboard
2. Click **Settings** → **Variables**
3. Add each variable above
4. Click **Deploy** to apply changes

### Getting Your Railway Public Domain

1. In Railway dashboard, click on your service
2. Look for **Domain** section
3. You'll see a URL like: `iamstech-production-xyz.railway.app`
4. This is your `IAMSTECH_BASE_URL`

**Example:**
```
IAMSTECH_BASE_URL=https://iamstech-production-xyz.railway.app
```

---

## 2. PRODUCTION LINK GENERATION VERIFICATION

### Before Going Live

Verify that the code properly generates production links:

```python
# Test in Railway logs after deployment
# Navigate to: https://your-domain/debug_errors
# Should show no "Invalid URL" errors

# Or check app logs directly via Railway CLI:
# railway logs --service your-service-name
```

### Expected Link Format

When admin approves an applicant, activation link should appear as:
```
https://iamstech-production-xyz.railway.app/setup-account/abc123def456
```

**NOT:**
- ~~http://localhost:5000/setup-account/...~~ (localhost)
- ~~http://192.168.x.x/setup-account/...~~ (internal IP)
- ~~http://railway.internal/setup-account/...~~ (internal Railway domain)

### Verification Steps

1. **Deploy the code** to Railway
2. **Register a test applicant** on the live site
3. **Verify OTP email** (or check fallback in logs)
4. **Admin approves** the applicant
5. **Check the approval flash message** for the manual activation link
6. **Copy the link** and verify it starts with `https://your-railway-domain`
7. **Open the link in browser** – should load the account setup page

---

## 3. FULL END-TO-END PRODUCTION TEST CHECKLIST

### Test Scenario: Complete Onboarding Flow

Run through this EXACT sequence on your Railway production deployment:

```
STEP 1: APPLICANT REGISTRATION
├─ Go to: https://your-domain/register
├─ Fill in:
│  ├─ Full Name: "Test Applicant"
│  ├─ Email: "test.applicant@example.com"
│  ├─ Phone: "+231 880 123456"
│  ├─ Department: "Information Technology"
│  └─ Profile Photo: (optional, but test file upload)
├─ Click "SUBMIT APPLICATION"
├─ Expected: "Registration successful! Please check your email."
└─ Check: User ID displayed in URL for next step

STEP 2: OTP VERIFICATION
├─ Go to: https://your-domain/verify-email/<USER_ID>
├─ Expected: OTP input page loads
├─ If SMTP working: Check email for 6-digit code
│  └─ Enter OTP and click "VERIFY & CONTINUE"
├─ If SMTP failed (expected fallback):
│  ├─ Page shows: "Having trouble receiving your verification code?"
│  ├─ WhatsApp support button visible
│  ├─ Check Railway logs for: "[OTP FALLBACK]" message with OTP code
│  ├─ Copy OTP from logs and enter it
│  └─ Click "VERIFY & CONTINUE"
└─ Expected: Verification success page displays

STEP 3: WAIT FOR ADMIN APPROVAL
├─ Login to: https://your-domain/dashboard (as SuperAdmin)
├─ Go to: "Pending Approvals" section
├─ You should see: "Test Applicant" in the queue
├─ Click: "Approve" button
└─ Expected: Flash message shows approval + manual activation link

STEP 4: CAPTURE ACTIVATION LINK
├─ From the approval flash message, copy the link
├─ Format should be: https://your-domain/setup-account/[UUID-TOKEN]
├─ DO NOT use localhost or internal IP
└─ Test: Paste link in NEW browser window/incognito

STEP 5: ACCOUNT SETUP (Activation)
├─ Link opens: "ACTIVATE ACCOUNT" page
├─ Page shows: Applicant name, institutional email, role
├─ Fill in:
│  ├─ New Password: "SecurePass123!"
│  └─ Confirm Password: "SecurePass123!"
├─ Click: "ACTIVATE PORTAL ACCESS"
└─ Expected: "Account setup complete! You can now log in."

STEP 6: LOGIN
├─ Go to: https://your-domain/login
├─ Login with:
│  ├─ Email: "test.applicant@example.com" (or institutional email)
│  └─ Password: "SecurePass123!"
├─ Click: "LOGIN"
└─ Expected: Redirected to /dashboard as Student

STEP 7: VERIFY DASHBOARD LOADS
├─ Dashboard should display without errors
├─ Check for:
│  ├─ Student profile section
│  ├─ Course listings
│  ├─ Navigation sidebar
│  ├─ Profile image rendering
│  └─ Responsive layout on mobile
└─ Mark: ✓ ONBOARDING FLOW COMPLETE
```

### Expected Outcomes

| Stage | Expected Behavior | Status |
|-------|-------------------|--------|
| Registration | User saved, ID generated | ✓ |
| OTP Sent | Email delivered OR fallback visible | ✓ |
| OTP Verified | State changes to `verified_awaiting_approval` | ✓ |
| Admin Approves | Setup token generated, activation link created | ✓ |
| Account Setup | Password set, token invalidated | ✓ |
| Login | User authenticated, dashboard loads | ✓ |

---

## 4. OTP FALLBACK VERIFICATION

### Railway Logs Monitoring

When OTP email fails in production:

```bash
# View logs in real-time
railway logs --service your-service --tail

# Look for patterns:
# "[OTP FALLBACK] Applicant: test@example.com OTP: 123456 Delivery Status: FAILED"
# or
# "[OTP SYSTEM] Dispatching to: ['test@example.com']"
```

### SuperAdmin Panel OTP Display

1. **Login as SuperAdmin** to https://your-domain/dashboard
2. **Go to "Global User Directory"** section
3. **Locate the test applicant** by name or email
4. **Check the "Verification & OTP" column:**
   - OTP badge shows: `OTP: 123456`
   - Status shows: `PENDING`, `SENT`, or `FAILED`
5. **Expected Display:**
   ```
   [OTP: 123456]
   ✉️ SENT  (or ⚠️ FAILED)
   ```

### Applicant Fallback Message

When email fails, applicant should see:

```
Having trouble receiving your verification code?

If your OTP does not arrive shortly, our Technical Support Team 
is available on WhatsApp to assist with account verification and onboarding.

[WhatsApp Support]  [Resend OTP]
```

---

## 5. FINAL UI VALIDATION

### Homepage Verification

1. **Navigate to:** https://your-domain/
2. **Check sections:**
   - [ ] Hero banner loads
   - [ ] Navigation bar responsive
   - [ ] Founder section displays with image (140x140px portrait)
   - [ ] Developer section displays with image (80x80px portrait - NEW COMPACT SIZE)
   - [ ] Programs grid displays cleanly
   - [ ] Activities section loads
   - [ ] Announcements display
3. **Mobile Test (375px width):**
   - [ ] No horizontal scroll
   - [ ] Images scale appropriately
   - [ ] Text readable without zoom

### Profile Card Validation

**Founder Portrait:**
- Size: 140x140px
- Appears premium and leadership-focused
- Spacing balanced with text

**Developer Portrait:**
- Size: 80x80px (COMPACT - true passport size)
- NOT oversized
- Professional team member appearance
- Spacing clean and aligned

### Dashboard Verification

1. **Login as Student/Admin/SuperAdmin**
2. **Check:**
   - [ ] Dashboard loads without JS errors
   - [ ] Profile avatar displays correctly
   - [ ] Sidebar navigation scrolls smoothly
   - [ ] Data tables render
   - [ ] Modals open/close properly
   - [ ] Dropdowns work

### Image Upload Testing

1. **As Admin, go to:** Founder/CEO Update section
2. **Upload a profile image** (500x500px or larger)
3. **Verify:**
   - [ ] File uploads successfully
   - [ ] Image displays in UI without distortion
   - [ ] Cropping/scaling looks professional

---

## 6. PRODUCTION STABILITY CHECKLIST

Before marking as production-ready:

### Database
- [ ] PostgreSQL migrations applied (if using Postgres)
- [ ] User table has all columns: `registration_state`, `otp_email_status`, `setup_token`, etc.
- [ ] Indexes created for performance
- [ ] Backup configured in Railway

### Email/SMTP
- [ ] `MAIL_USERNAME` set to correct SMTP provider
- [ ] `MAIL_PASSWORD` is app-specific password (not account password)
- [ ] `MAIL_DEFAULT_SENDER` configured
- [ ] Fallback mode logging verified

### SSL/HTTPS
- [ ] Railway auto-SSL enabled
- [ ] All links use `https://`
- [ ] Mixed content warnings resolved

### Performance
- [ ] Homepage loads in < 3 seconds
- [ ] Dashboard loads in < 2 seconds
- [ ] Image optimization applied

### Security
- [ ] `SECRET_KEY` is strong random string (not default)
- [ ] `DEV_MODE=false` in production
- [ ] No debug info exposed in error pages
- [ ] CSRF protection enabled

### Logging
- [ ] Application logs visible in Railway dashboard
- [ ] Error logs captured and searchable
- [ ] OTP fallback messages logged for admin visibility

---

## 7. PRODUCTION TROUBLESHOOTING

### Problem: Activation Link Shows Localhost

**Fix:**
1. Go to Railway Variables
2. Add/update: `IAMSTECH_BASE_URL=https://your-railway-domain.railway.app`
3. Click Deploy
4. Wait 1-2 minutes for restart
5. Test registration again

### Problem: OTP Email Not Arriving (But SMTP Configured)

**Check:**
1. Verify `MAIL_USERNAME` and `MAIL_PASSWORD` are correct
2. Check Railway logs for `[OTP FALLBACK]` messages
3. Confirm SMTP provider allows external connections
4. Test with a known working email first

### Problem: Setup Link Expired

**Expected Behavior:**
- Links are valid for **72 hours**
- User sees: "Setup link expired. Please contact administration."
- Admin can re-approve to generate new link

### Problem: User Can't Login After Setup

**Check:**
1. Verify `registration_state` is `approved`
2. Verify `is_email_verified` is `True`
3. Check password was saved correctly
4. Try password reset flow if needed

---

## 8. DEPLOYMENT SUCCESS CRITERIA

You can consider production deployment **COMPLETE** when:

| Criterion | Verification |
|-----------|--------------|
| Base URL Configured | IAMSTECH_BASE_URL set in Railway Variables |
| Activation Links Work | Link from approval email opens setup page |
| Full Onboarding | Test applicant completes all 7 steps successfully |
| OTP Fallback | Logs show OTP code when email fails |
| SuperAdmin Visibility | OTP visible in admin panel |
| UI Polished | Images display correctly, profiles compact |
| No Errors | Zero 500 errors in production logs |
| Security | No secrets exposed, HTTPS enforced |

---

## 9. NEXT STEPS

1. **Set Railway Variables** (Section 1)
2. **Deploy Code** to Railway
3. **Run Full E2E Test** (Section 3)
4. **Validate UI** (Section 5)
5. **Monitor Logs** for 24 hours
6. **Go Live** with confidence

---

## 10. SUPPORT & DOCUMENTATION

For ongoing issues:
- Check Railway dashboard **Logs** tab
- Review this guide's troubleshooting section
- Contact Railway support for infrastructure issues

---

**Prepared by:** Development Team  
**For:** IAMSTECH School Management System  
**Audience:** DevOps / System Administrator  
**Confidential:** Internal Use Only
