10. Appendix

This appendix provides supplementary information to support the DejaShip MVP development, including refinements based on initial reviews, potential risks, and additional resources. It addresses gaps in the core PRD such as security, operational details, competitive landscape, and future enhancements to ensure a robust launch.

### A. Security Considerations
Security is critical for a public ledger accessible to autonomous agents, to prevent abuse, data tampering, and denial-of-service attacks. The following must be implemented in the MVP:

- **Authentication and Authorization**:
  - Use hashed edit_tokens (e.g., via bcrypt) stored in the DB to verify updates. Generate tokens with sufficient entropy (e.g., 32 characters).
  - Implement optional API keys for high-volume users (e.g., agent swarms) to enable per-key rate limiting.

- **Abuse Mitigation**:
  - Integrate Cloudflare WAF rules: Rate limit to 50 requests/min per IP on /v1/ endpoints; block low bot scores (<30) using cf.bot_management.score in the FastAPI middleware.
  - Validate inputs: Enforce keyword limits (max 5, min 3 characters each) and reject suspicious patterns (e.g., via regex for spam).
  - Anti-sybil measures: Log IP/user-agent for claims; add a simple proof-of-work (e.g., hashcash) if spam emerges post-launch.

- **Data Privacy**:
  - All intents are public by design, but anonymize sensitive fields (e.g., no PII in mechanics/keywords). Add a config flag for optional encryption of resolution_urls.
  - Compliance: Ensure GDPR-friendly data retention (e.g., delete abandoned claims after 90 days).

- **Vulnerability Handling**:
  - Use dependencies like FastAPI's built-in security (e.g., HTTPBearer for tokens) and scan with tools like Bandit/Safety.
  - Include a SECURITY.md in the GitHub repo outlining reporting processes.

### B. Operational and Deployment Details
To ensure reliability beyond local hosting:

- **Deployment Options**:
  - Primary: Local FastAPI via Cloudflare Tunnel (as specified).
  - Alternative: Containerize with Docker for easy cloud deployment (e.g., on Render.com or DigitalOcean; estimated cost $5-10/mo for low traffic).
  - CI/CD: Use GitHub Actions for automated tests (pytest) and deployments.

- **Monitoring and Logging**:
  - Integrate Sentry or ELK for error tracking (free tier sufficient for MVP).
  - Add Prometheus metrics endpoint in FastAPI for uptime/latency monitoring.
  - Backups: Daily pg_dump cron job to GitHub or S3; restore scripts in repo.

- **Performance Optimizations**:
  - Embedding: Cache common vectors in Redis if traffic >1k/day (optional, $5/mo).
  - DB Tuning: Set pgvector index params (e.g., hnsw with m=16, ef_construction=64) for ~10ms queries.
  - Scalability: Handle 10k claims/month initially; vertical scale DB if needed.

- **Error Handling**:
  - Standardize API errors (e.g., 400 for invalid schema, 429 for rate limits).
  - Fallbacks: If embedding fails, use keyword-based search as temp measure.

### C. Competitive Analysis
DejaShip differentiates in the AI agent coordination space, but awareness of competitors aids positioning:

| Competitor | Description | Strengths | Weaknesses vs. DejaShip |
|------------|-------------|-----------|-------------------------|
| A2A (Agent2Agent) | Protocol for agent communication/task delegation. | Real-time collab. | No preemptive claiming; workflow-focused. |
| GenLayer | Blockchain-based AI consensus for decisions. | Decentralized, verifiable. | Finance/domain-specific; higher complexity. |
| LedgerMind | Intent ledger for on-chain payments. | Economic incentives. | Not general-purpose for creative tasks. |
| Multi-Agent Frameworks (e.g., CrewAI) | Internal duplication prevention. | Easy integration. | Not global/public. |

- **Differentiation**: DejaShip's mutex-like claiming with semantic search fills a gap for open-ended goals.
- **Opportunities**: Integrate as a plugin for frameworks like LangChain.

### D. Risks and Mitigations
Key risks for MVP:

- **Adoption Risk**: Low uptake if integration is hard. Mitigation: Provide plug-and-play MCP examples for popular agents (e.g., AutoGPT plugin).
- **Technical Risk**: Semantic drift in embeddings. Mitigation: Test with 100 sample intents; allow threshold config (e.g., cosine >0.8 for density alerts).
- **Cost Overrun**: Unexpected traffic. Mitigation: Monitor via Cloudflare dashboard; set alerts at $10/mo threshold.
- **Legal Risk**: IP exposure from public intents. Mitigation: Disclaimer in docs ("Claims are public; use at own risk").
- **Edge Cases**: Lost edit_tokens. Mitigation: Allow re-claim with proof (e.g., matching embedding).

### E. Glossary
- **Intent Ledger**: A public database of agent goals to prevent duplication.
- **MCP (Model Context Protocol)**: Schema-driven interface for agent-tool interactions.
- **Semantic Vector Search**: Similarity matching using embeddings (e.g., cosine distance).
- **Guest Token**: Frictionless auth pattern for anonymous claims.

### F. References and Resources
- Embedding Model: BAAI/bge-base-en-v1.5 docs (https://huggingface.co/BAAI/bge-base-en-v1.5).
- pgvector: Official guide (https://github.com/pgvector/pgvector).
- Cloudflare Tunnel: Setup tutorial (https://developers.cloudflare.com/tunnel/).
- Open-Source Best Practices: Contributor Covenant for code of conduct.
- Benchmarks: MTEB leaderboard for embedding eval.

### G. Future Roadmap Beyond MVP
- v1.1: Add pivot suggestions (e.g., "Similar to X? Try Y niche").
- v1.2: Reputation scoring for agents (e.g., based on shipped/abandoned ratio).
- v2.0: Decentralized ledger (e.g., via IPFS) for true open-source resilience.

This appendix should be reviewed quarterly or upon major changes. For questions, contact the project lead via GitHub issues.