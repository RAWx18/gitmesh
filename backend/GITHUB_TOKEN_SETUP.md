# GitHub Token Setup Guide

## Why do you need a GitHub token?

A GitHub Personal Access Token allows your application to:
- Access private repositories
- Increase API rate limits (5000 requests/hour vs 60 for unauthenticated)
- Avoid rate limiting issues when fetching repository data

## How to create a GitHub Personal Access Token

1. **Go to GitHub Settings**
   - Visit: https://github.com/settings/tokens/new?description=gitingest&scopes=repo
   - Or manually: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)

2. **Configure the token**
   - **Note**: `GitMesh Repository Access`
   - **Expiration**: Choose your preferred expiration (90 days recommended)
   - **Scopes**: Select the following permissions:
     - ✅ `repo` (Full control of private repositories)
     - ✅ `public_repo` (Access public repositories)

3. **Generate and copy the token**
   - Click "Generate token"
   - **IMPORTANT**: Copy the token immediately (you won't see it again!)

4. **Add to your .env file**
   ```bash
   # Replace the empty GITHUB_TOKEN with your actual token
   GITHUB_TOKEN=ghp_your_actual_token_here
   ```

## Security Notes

- ⚠️ **Never commit your token to version control**
- ⚠️ **Keep your token secure and private**
- ⚠️ **Regenerate tokens periodically**
- ⚠️ **Use environment variables, not hardcoded values**

## Testing your token

After adding your token to `.env`, restart your application and check the logs:
- ✅ You should see: "GitHub token available for authenticated requests"
- ❌ If you see: "No valid GitHub token", check the token format

## Without a token

The application will still work for public repositories, but with limitations:
- Lower rate limits (60 requests/hour)
- No access to private repositories
- Potential rate limiting during heavy usage

## Troubleshooting

**"Invalid GitHub token format" error:**
- Make sure your token starts with `ghp_` (for classic tokens)
- Ensure there are no extra spaces or characters
- Verify the token hasn't expired

**Rate limiting issues:**
- Add a valid GitHub token to increase limits
- Wait for rate limit reset (usually 1 hour)
- Use fewer concurrent requests