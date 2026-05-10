# IAMSTECH Production Deployment Checklist

**Project:** IAMSTECH School Management Mini System  
**Status:** Ready for Railway Production Deployment  
**Last Updated:** May 9, 2026

---

## PRE-DEPLOYMENT CHECKLIST

### Code Changes Made

- [x] Production URL handling added (`IAMSTECH_BASE_URL` env var)
- [x] Email link generation hardened with `build_external_url()` helper
- [x] Activation route aliases added (`/setup-password/<token>`)
- [x] OTP fallback messaging improved on verification page
- [x] Account setup page guidance added
- [x] Developer portrait reduced to 80x80px (true passport size)
- [x] Founder portrait balanced at 140x140px
- [x] Profile card spacing optimized
- [x] SuperAdmin OTP visibility confirmed
- [x] Error handling in place for all critical paths

### Files Modified

```
✓ app.py
  - Added BASE_URL configuration
  - Added SERVER_NAME mapping
  - Imported build_external_url
  - Added /setup-password/<token> route alias
  - OTP failure messaging improved

✓ email_service.py
  - Added build_external_url() helper function
  - Updated approval email to use build_external_url()
  - Updated reset email to use build_external_url()
  - Maintained SMTP fallback logging

✓ templates/verify_email.html
  - Professional OTP failure alert
  - WhatsApp support button prominently displayed
  - Resend OTP action available
  - Mobile responsive

✓ templates/setup_account.html
  - Account activation guidance added
  - WhatsApp support CTA visible
  - Shows institutional email/role
  - Mobile responsive

✓ static/css/style.css
  - Developer portrait reduced to 80x80px
  - Founder portrait set to 140x140px
  - Profile spacing optimized
  - Responsive adjustments applied
```

---

## RAILWAY DEPLOYMENT STEPS

### Step 1: Configure Environment Variables

Access Railway Project Dashboard → Settings → Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `IAMSTECH_BASE_URL` | `https://your-service-name.railway.app` | **Critical** - Replace with your actual Railway domain |
| `MAIL_USERNAME` | `your-email@gmail.com` | SMTP sender email |
| `MAIL_PASSWORD` | `your-app-password` | App-specific password (not account password) |
| `MAIL_DEFAULT_SENDER` | `noreply@iamstech.edu.lr` | From email header |
| `SECRET_KEY` | `[strong-random-string]` | Use `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEV_MODE` | `false` | Production mode |
| `IAMSTECH_REG_SAFE_MODE` | `false` | Normal email dispatch (not safe mode) |
| `DATABASE_URL` | (if PostgreSQL) | Auto-configured if using Railway PostgreSQL |

### Step 2: Deploy to Railway

```bash
# Via Railway CLI:
railway up

# Or push to GitHub and Railway auto-deploys (if configured)
git push origin main
```

### Step 3: Verify Deployment

```bash
# Check logs
railway logs

# Should see:
# "Running on https://your-service.railway.app"
# No errors or exceptions
```

### Step 4: Monitor First 30 Minutes

Watch for:
- No 500 errors
- Database migrations ran successfully
- Email dispatch working (or falling back to logs)
- Users can access homepage

---

## PRODUCTION TEST EXECUTION PLAN

### Phase 1: Quick Smoke Test (10 minutes)

1. [ ] **Homepage loads**
   ```
   Visit: https://your-domain/
   Expected: Page loads, no 500 errors
   ```

2. [ ] **Registration page accessible**
   ```
   Click: "Register" button
   Expected: Registration form loads
   ```

3. [ ] **Login page works**
   ```
   Visit: https://your-domain/login
   Expected: Login form displays
   ```

### Phase 2: OTP Fallback Test (15 minutes)

1. [ ] **Register test applicant**
   ```
   Name: "OTP Test User"
   Email: "otp-test@example.com"
   Phone: "+231 880 000001"
   Dept: "IT"
   Expected: Redirect to /verify-email page
   ```

2. [ ] **Check OTP in Railway logs**
   ```
   Railway Dashboard → Logs
   Search for: "[OTP FALLBACK]"
   Expected: OTP code visible
   Format: "OTP: 123456"
   ```

3. [ ] **Enter OTP and verify**
   ```
   Copy OTP from logs
   Enter on /verify-email page
   Click: "VERIFY & CONTINUE"
   Expected: Verification success page
   ```

### Phase 3: Approval & Activation Test (15 minutes)

1. [ ] **Admin approves applicant**
   ```
   Login as SuperAdmin
   Go to: Pending Approvals section
   Click: Approve button
   Expected: Approval message shows activation link
   Format: https://your-domain/setup-account/[UUID]
   ```

2. [ ] **Extract and test activation link**
   ```
   Copy link from approval message
   Open in NEW browser window
   Expected: Account setup form loads
   ```

3. [ ] **Complete account setup**
   ```
   Password: "TestPass123!"
   Confirm: "TestPass123!"
   Click: "ACTIVATE PORTAL ACCESS"
   Expected: Setup success page
   ```

4. [ ] **Test login**
   ```
   Visit: https://your-domain/login
   Email: "otp-test@example.com"
   Password: "TestPass123!"
   Click: "LOGIN"
   Expected: Dashboard loads as Student
   ```

### Phase 4: UI Validation (10 minutes)

**Homepage:**
- [ ] Hero section displays
- [ ] Navigation bar responsive
- [ ] Founder image: Professional size (140x140), leadership-focused
- [ ] Developer image: Compact size (80x80), passport-like
- [ ] No image distortion or overflow
- [ ] Activities load correctly
- [ ] Announcements display

**Mobile (375px width):**
- [ ] No horizontal scroll
- [ ] Images scale down gracefully
- [ ] Text readable
- [ ] Buttons clickable

**Dashboard:**
- [ ] Sidebar navigation works
- [ ] Profile section displays
- [ ] Tables render correctly
- [ ] Modals open/close

---

## ROLLBACK PROCEDURE

If critical issues occur:

```bash
# View Railway releases
railway docs

# Revert to previous deployment
railway rollback [previous-version-id]

# Or via GitHub, revert commit and push
git revert [commit-hash]
git push origin main
```

---

## SUCCESS VALIDATION

### Checklist for "Production Ready"

Complete **ALL** of these before considering deployment successful:

```
CONFIGURATION
  ☐ IAMSTECH_BASE_URL set to your Railway domain
  ☐ MAIL credentials configured
  ☐ SECRET_KEY set to random string
  ☐ DEV_MODE = false
  ☐ IAMSTECH_REG_SAFE_MODE = false

FUNCTIONALITY
  ☐ Homepage loads without errors
  ☐ Registration form accessible
  ☐ OTP generation works
  ☐ OTP fallback visible in logs
  ☐ OTP fallback message shows to applicant
  ☐ Admin approval generates correct activation link
  ☐ Activation link opens with production domain
  ☐ Account setup completes successfully
  ☐ User can login after setup
  ☐ Dashboard renders correctly

UI VALIDATION
  ☐ Founder image displays at 140x140px
  ☐ Developer image displays at 80x80px (COMPACT)
  ☐ Profile cards look professional
  ☐ No image distortion
  ☐ Mobile responsive (tested at 375px)
  ☐ Navigation works on all pages

SECURITY
  ☐ All links use https://
  ☐ No localhost references in links
  ☐ CSRF protection enabled
  ☐ No debug info in error pages
  ☐ Secrets not logged

LOGS & MONITORING
  ☐ Zero 500 errors in first hour
  ☐ Email dispatch logged (or fallback logged)
  ☐ OTP codes visible in logs for troubleshooting
  ☐ Admin can see OTP in SuperAdmin panel
```

---

## PRODUCTION SUPPORT

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Activation link shows localhost | `IAMSTECH_BASE_URL` not set | Set env var in Railway Variables |
| OTP not in logs | Email sent successfully | Check email inbox, not a failure |
| OTP visible in logs but applicant can't use it | OTP expired | Wait 15 min for new OTP, have them request new |
| User can't login after setup | Registration not fully approved | Check `registration_state` in DB |
| Email not sending | SMTP credentials wrong | Verify `MAIL_USERNAME` and `MAIL_PASSWORD` |

### Monitoring Checklist (Daily)

```
□ Check Railway logs for errors
□ Verify new users can complete onboarding
□ Monitor SMTP delivery success rate
□ Check database connectivity
□ Verify SSL certificate still valid
□ Monitor application response times
```

---

## HANDOFF DOCUMENTATION

### What's Been Completed

**Architecture:**
- Flask app with ProxyFix for Railway
- PostgreSQL or SQLite database
- Async email dispatch with fallback logging
- JWT-style setup tokens with expiration
- Comprehensive error handling

**Features:**
- User registration with email verification
- 6-digit OTP with 15-minute expiration
- Admin approval workflow
- Setup token activation (72 hours)
- Password reset capability
- SuperAdmin control panel

**Reliability:**
- OTP fallback when email fails
- Token expiration handling
- Registration state machine
- Audit logging
- Clean error pages

**UI/UX:**
- Responsive design
- Professional color scheme
- WhatsApp support integration
- Clear onboarding guidance
- Accessible forms

### Maintenance Tasks

**Weekly:**
- Review production logs for errors
- Test new user registration
- Verify email delivery

**Monthly:**
- Review SuperAdmin audit logs
- Check database performance
- Update dependencies (if needed)

**Quarterly:**
- Review and update security policies
- Plan infrastructure upgrades if needed
- Assess user feedback

---

## CONTACT & ESCALATION

For production issues:

1. **Check this guide** (Troubleshooting section)
2. **Review Railway logs**
3. **Test locally** if possible
4. **Contact Railway support** for infrastructure issues

---

**Prepared By:** Development Team  
**Date:** May 9, 2026  
**Version:** 1.0  
**Status:** Ready for Production Deployment
