# IAMSTECH Production Deployment - Quick Start Guide

**Time to Deploy:** 5 minutes  
**Time to Validate:** 30 minutes  
**Status:** READY NOW

---

## STEP 1: DEPLOY TO RAILWAY (5 minutes)

### 1.1 Set Environment Variables

Go to: https://railway.app → Your Project → Settings → Variables

Add these 7 variables:

```
IAMSTECH_BASE_URL=https://your-railway-domain.railway.app
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=noreply@iamstech.edu.lr
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
DEV_MODE=false
IAMSTECH_REG_SAFE_MODE=false
```

**Where to find your Railway domain:**
- Settings → Domain → Copy the URL (looks like: `service-xyz.railway.app`)

### 1.2 Deploy Code

Option A: Via Git Push (Recommended)
```bash
git add .
git commit -m "Production deployment: URL handling, OTP fallback, UI polish"
git push origin main
```

Option B: Via Railway CLI
```bash
railway up
```

Wait 2-3 minutes for deployment to complete.

### 1.3 Verify Deployment

Check Railway logs: Should see no 500 errors and homepage loads.

---

## STEP 2: VALIDATE END-TO-END (30 minutes)

Run through this **exact sequence**:

### 2.1 Register Test Applicant
```
1. Visit: https://your-domain/register
2. Enter:
   - Name: "Test Applicant"
   - Email: "test@example.com"
   - Phone: "+231 880 123456"
   - Department: "IT"
3. Click: SUBMIT APPLICATION
4. Expected: Redirected to OTP verification page
```

### 2.2 Verify OTP (Two Scenarios)

**Scenario A - Email Works:**
- Check email for OTP
- Enter OTP on verification page
- Click: VERIFY & CONTINUE
- Expected: Verification success

**Scenario B - Email Fails (Expected):**
1. Go to Railway Logs
2. Search for: `[OTP FALLBACK]`
3. Copy the OTP code from logs
4. Enter on verification page
5. Click: VERIFY & CONTINUE
6. Expected: Verification success

### 2.3 Admin Approves

```
1. Login as SuperAdmin
2. Go to: Pending Approvals
3. Find: "Test Applicant"
4. Click: Approve
5. Copy the activation link from the message
6. Important: Link should start with https://your-domain
```

### 2.4 Test Account Setup

```
1. Paste the activation link in a NEW browser window
2. Expected: "ACTIVATE ACCOUNT" page loads
3. Set password: "TestPass123!"
4. Click: ACTIVATE PORTAL ACCESS
5. Expected: Account setup success page
```

### 2.5 Test Login

```
1. Go to: https://your-domain/login
2. Enter:
   - Email: test@example.com
   - Password: TestPass123!
3. Click: LOGIN
4. Expected: Redirected to dashboard
```

### 2.6 Verify UI Rendering

```
Homepage:
  [ ] Founder image displays at proper size (140x140)
  [ ] Developer image is compact (80x80)
  [ ] Programs section displays
  [ ] No distorted images

Dashboard:
  [ ] Sidebar works
  [ ] Profile section displays
  [ ] Tables render correctly
  
Mobile (375px):
  [ ] No horizontal scroll
  [ ] Images scale properly
  [ ] Text readable
```

---

## STEP 3: VERIFY OTP FALLBACK (2 minutes)

This is critical for production reliability.

### What to Check

1. **Railway Logs:**
   ```
   Search for: "[OTP FALLBACK]"
   Expected format: "Applicant: test@example.com OTP: 123456 Delivery Status: FAILED"
   ```

2. **SuperAdmin Panel:**
   - Login as SuperAdmin
   - Go to: Global User Directory
   - Find test applicant
   - Check: Verification & OTP column
   - Expected: OTP code visible, status shows PENDING or FAILED

3. **Applicant Experience:**
   - On verification page, applicant should see:
     ```
     Having trouble receiving your verification code?
     If your OTP does not arrive shortly, our Technical Support Team 
     is available on WhatsApp...
     [WhatsApp Support] [Resend OTP]
     ```

---

## STEP 4: FINAL VALIDATION (2 minutes)

```
Checklist:

CONFIGURATION
  [ ] IAMSTECH_BASE_URL set in Railway Variables
  [ ] Activated links use production domain (not localhost)
  [ ] MAIL credentials working (or fallback visible)

FUNCTIONALITY  
  [ ] Registration → OTP → Approval → Setup → Login works
  [ ] OTP visible in Railway logs when email fails
  [ ] OTP visible in SuperAdmin panel
  [ ] Applicant sees professional fallback message

UI
  [ ] Homepage loads
  [ ] Profile images display correctly
  [ ] Developer image is truly compact (80x80)
  [ ] Mobile responsive

PRODUCTION READY
  [ ] No 500 errors in logs
  [ ] All links use https://
  [ ] No localhost references
```

If ALL checked: **DEPLOYMENT SUCCESSFUL**

---

## TROUBLESHOOTING QUICK FIX

| Problem | Solution |
|---------|----------|
| Activation link shows localhost | Add `IAMSTECH_BASE_URL` to Railway Variables |
| Page says "Internal Server Error" | Check Railway logs for specific error |
| OTP not arriving by email | Check Railway logs for `[OTP FALLBACK]` entry |
| User can't login after setup | Verify `registration_state` is `approved` in database |

---

## WHAT WAS CHANGED

### Code Updates
- ✓ Production URL handling
- ✓ Activation link generation
- ✓ OTP fallback messaging
- ✓ Profile image sizing
- ✓ UI polish and guidance

### Documentation Created
- ✓ PRODUCTION_DEPLOYMENT_GUIDE.md (detailed reference)
- ✓ DEPLOYMENT_CHECKLIST.md (step-by-step validation)
- ✓ FINAL_DEPLOYMENT_SUMMARY.md (comprehensive overview)
- ✓ CHANGELOG.md (all code changes)
- ✓ This quick start guide

---

## MONITORING CHECKLIST (Post-Deployment)

**First Hour:**
- [ ] Check logs every 10 minutes
- [ ] No 500 errors appearing
- [ ] Application responding normally

**First 24 Hours:**
- [ ] Monitor general error rate
- [ ] Test new registrations every few hours
- [ ] Verify email or fallback working

**One Week:**
- [ ] Review all registration attempts
- [ ] Check OTP delivery success rate
- [ ] Monitor application performance

---

## SUPPORT RESOURCES

Need help? Check these files in order:

1. **DEPLOYMENT_CHECKLIST.md** - Detailed step-by-step validation
2. **PRODUCTION_DEPLOYMENT_GUIDE.md** - Comprehensive troubleshooting
3. **FINAL_DEPLOYMENT_SUMMARY.md** - Full architecture overview
4. **CHANGELOG.md** - All code changes made

---

## YOU'RE READY 🚀

This quick start guide covers:
- ✓ Deploying to Railway
- ✓ Validating end-to-end
- ✓ Verifying OTP fallback
- ✓ Final checks

**Estimated total time: 40 minutes**

Start with **STEP 1** above and follow each step in order.

---

**Questions?** Open one of the supporting guides. They have detailed answers for every scenario.

**Status:** Ready for immediate production deployment.
