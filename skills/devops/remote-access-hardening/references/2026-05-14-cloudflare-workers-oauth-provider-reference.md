# Cloudflare Workers OAuth Provider — Reference Note

**Repo:** https://github.com/cloudflare/workers-oauth-provider
**Stars:** ~1,774 | **Language:** TypeScript | **Forks:** 120

## What is it

TypeScript library implementing the **provider side of OAuth 2.1 protocol with PKCE support** for Cloudflare Workers. The library wraps your Worker code and handles all token management automatically.

## Key Benefits

- Acts as a wrapper around Worker code, adding authorization for API endpoints
- All token management handled automatically (no secrets stored, only hashes)
- API handler receives pre-authenticated user details as a parameter
- Agnostic to user management (any auth system works underneath)
- Agnostic to UI framework (any frontend works)
- No external database required for token storage

## Usage Pattern

```ts
import { OAuthProvider } from '@cloudflare/workers-oauth-provider';
import { WorkerEntrypoint } from 'cloudflare:workers';

export default new OAuthProvider({
  apiRoute: ['/api/', 'https://api.example.com/'],
  // The API handler receives authenticated user details
  apiHandler: new MyAPIHandler(),
  // Token storage implementation
  tokenStorage: new MyTokenStorage(),
});
```

## Relevance to Hermes

Hermes already does OAuth for providers (MiniMax OAuth, openai-codex). This library shows a mature, production-grade OAuth 2.1 + PKCE implementation pattern that could inform:
- Future OAuth provider improvements in Hermes
- If Hermes ever adds its own OAuth-protected API endpoints
- Token storage patterns (stateless, no DB required)

## Links
- Repo: https://github.com/cloudflare/workers-oauth-provider
- Workers runtime: `cloudflare:workers`