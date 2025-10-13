# Secure Web Interface for Harvest Sheet

This directory contains a secure web interface for the Harvest Sheet application, implementing multiple layers of security for safe deployment on GitHub Pages.

## Security Features

### 🔐 Multi-Layer Authentication
- **Google OAuth 2.0**: Users must sign in with authorized Google accounts
- **Server-side Authorization**: User whitelist validated in GitHub Actions (not client-side)
- **Manual Workflow Trigger**: No hardcoded GitHub tokens - users manually trigger workflows
- **Input Sanitization**: All user inputs validated and sanitized server-side
- **CSRF Protection**: Tokens generated for each request

### 🛡️ Data Protection
- **No Hardcoded Secrets**: All sensitive data stored in GitHub repository secrets
- **Token Hashing**: OAuth tokens hashed client-side, never transmitted in plain text
- **Audit Logging**: Complete security audit trail for all actions
- **Parameter Validation**: Strict format validation for dates, emails, and user inputs
- **Secure Environment Variables**: Credentials loaded without exposure in logs

### 🚨 Attack Prevention
- **XSS Prevention**: Input sanitization removes dangerous characters
- **Injection Prevention**: Shell command injection blocked via input validation
- **Unauthorized Access**: Email-based whitelist enforced server-side
- **Rate Limiting**: Basic request throttling and monitoring
- **Error Handling**: Secure error messages without information disclosure

## How It Works

### 1. User Authentication Flow
```
User → Google OAuth → Frontend → Parameter Generation → Manual GitHub Trigger
```

1. User signs in with Google OAuth 2.0
2. Frontend generates secure, sanitized parameters
3. User manually triggers GitHub Actions workflow
4. Server validates authorization and executes harvest script

### 2. Security Validation Chain

#### Client-Side (docs/app.js):
- Google OAuth token verification
- Input sanitization and length limits
- CSRF token generation
- OAuth token hashing (SHA-256)
- Parameter formatting and validation

#### Server-Side (GitHub Actions):
- Email whitelist validation against secrets
- Input format validation (regex patterns)
- Parameter sanitization (removal of dangerous characters)
- Security audit logging
- Credential loading without exposure

## Setup Instructions

### 1. Configure Google OAuth
```bash
# Google Cloud Console:
# 1. Create OAuth 2.0 Client ID
# 2. Add GitHub Pages URL to authorized origins
# 3. Copy Client ID to docs/app.js
```

### 2. Set Repository Secrets
```bash
# Required secrets:
ALLOWED_USERS=user1@example.com,user2@example.com

# Google Service Account:
GOOGLE_SA_PROJECT_ID=your-project-id
GOOGLE_SA_PRIVATE_KEY=your-private-key
# ... (see setup guide for complete list)

# User-specific secrets:
USER1_HARVEST_ACCOUNT_ID=123456
USER1_HARVEST_AUTH_TOKEN=your-token
# ... (for each user)
```

### 3. Enable GitHub Pages
```bash
# Repository Settings → Pages:
# Source: Deploy from branch
# Branch: main
# Folder: /docs
```

### 4. Update Configuration
```javascript
// Edit docs/app.js:
CONFIG.GOOGLE_CLIENT_ID = 'your-actual-client-id';
CONFIG.GITHUB_OWNER = 'your-username';
CONFIG.GITHUB_REPO = 'your-repo-name';
```

## File Structure

```
docs/
├── index.html          # Main web interface
├── app.js             # Secure JavaScript logic
└── README.md          # This file

.github/workflows/
└── web-trigger.yml    # Secure GitHub Actions workflow
```

## Security Considerations

### ✅ Safe for Public Repositories
- No hardcoded tokens or secrets
- Client-side authorization is informational only
- All security validation happens server-side
- Audit logging for compliance and monitoring

### 🔒 Additional Security Measures
- All credentials stored as GitHub repository secrets
- OAuth tokens hashed before transmission
- Input validation prevents injection attacks
- Manual trigger prevents automated abuse
- Complete audit trail for security monitoring

### 📋 Security Testing
```bash
# Test checklist:
□ Unauthorized email cannot access system
□ Invalid date formats are rejected
□ Special characters are sanitized
□ OAuth tokens are never logged in plain text
□ Manual workflow trigger is required
□ All secrets remain in repository secrets
```

## Usage

1. **Visit GitHub Pages URL**: `https://yourusername.github.io/yourrepo`
2. **Sign in with Google**: Use authorized Google account
3. **Fill Parameters**: Select date range and options
4. **Get Instructions**: System generates secure parameters
5. **Manual Trigger**: Go to GitHub Actions and run workflow manually
6. **Download Results**: Get files from workflow artifacts

## Troubleshooting

### Common Issues
- **"Access denied"**: Email not in ALLOWED_USERS secret
- **"Invalid format"**: Check date format (YYYY-MM-DD)
- **"Credentials not found"**: Verify repository secrets are set
- **"Workflow not found"**: Check workflow file exists and is enabled

### Security Alerts
- **Never** commit OAuth client secrets to repository
- **Always** use HTTPS for authentication flows
- **Regularly** rotate personal access tokens
- **Monitor** workflow logs for suspicious activity

## Architecture Benefits

This secure architecture provides:
- **Zero client-side secrets**: Safe for public repositories
- **Defense in depth**: Multiple security layers
- **Audit compliance**: Complete logging and monitoring
- **Attack resistance**: Input validation and sanitization
- **User convenience**: Simple web interface with Google OAuth
- **Maintainability**: Clear separation of concerns

The implementation prioritizes security while maintaining full functionality on GitHub Pages + GitHub Actions.