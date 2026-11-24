# Smartphone Link Plan — Machine God / Zero40

Status: PLANNED.

## Plan

### Architecture (reuse existing bridges)
The smartphone link reuses the existing omega android / remote / handy bridges referenced in the repo inventory. The phone talks to the local Machine God via LAN (Tailscale / WireGuard / local Wi-Fi). No public internet exposure. The phone is a *view* into the same EntityOS/GRID/Retina that the TUI uses — not a second agent.

```
[Phone] <-- HTTPS/TLS (LAN via omega android/remote/handy bridges) --> [Machine God HTTP API : 8765]
                                                      |
                                                      v
                                    +-----------------+-----------------+
                                    |                                 |
                              [GRID : 8490]                      [EntityOS / unified.db]
                                    |                                 |
                              [Retina CLI]                      [Omnipool : 8080]
                                    |                                 |
                              [0.8B Ground Mode : 8111]             [Claude Code (opt-in)]
```

### Components to Build / Reuse

| Component | Source | Status |
|-----------|--------|--------|
| HTTP API (Rust, axum) | New in `src/zero/api.rs` | PLANNED |
| Capability token (Ed25519, short-lived, revocable) | New in `src/zero/auth.rs` | PLANNED |
| Phone UI (PWA) | Reuse: `agentic-grid` chat hub pattern | PLANNED |
| Push / WebSocket for async replies | Reuse: `agentic-grid` WebSocket hub | PLANNED |
| QR code pairing (token exchange) | Reuse: omega android / remote / handy bridges | PLANNED |
| GRID push notification → phone | Existing omega android bridge | PLANNED |

### Smallest working piece
**GRID push notification → phone via existing omega android bridge.**

1. TUI or GRID emits a test notification event (kind=`grid_push`, payload text).
2. Event is pushed to loopback GRID (`127.0.0.1:8490`) and persisted to `unified.db`.
3. Existing omega android bridge receives the event from the local Machine God API over LAN.
4. Phone displays the test notification.

This is the smallest piece because it reuses the omega android bridge transport and adds only the GRID→phone push path.

### Acceptance

| Criterion | Evidence | Status |
|-----------|----------|--------|
| Phone receives test notification | GRID push event delivered to phone via omega android bridge | PLANNED |
| Notification contains status line | `GRID ok | Retina ok | EntityOS ok | Omnipool ok` or `UNKNOWN` when unmeasured | PLANNED |
| Loopback/LAN only enforced | No public IP in config; code enforces loopback/LAN CIDRs | PLANNED |
| No secrets on phone | Phone holds only a revocable capability token; no model weights, `unified.db`, or API keys | PLANNED |

Status: PLANNED.

### Constraints (Hard)
- **Loopback only**: The phone talks to the local machine via LAN. No public internet exposure.
- **No secrets on the phone**: The phone holds only a revocable capability token; all keys, model weights, and `unified.db` stay on the host.
- **Single entity**: The phone is a *view* into the same EntityOS/GRID/Retina that the TUI uses — not a second agent.
- **Free pool only by default**: Phone traffic routes through Omnipool (local free models). Claude Code path is opt-in from the TUI.

### API Surface (Minimal v1)

```
POST   /api/v1/chat          { message: string, session_id?: string } -> { reply: string, session_id: string }
GET    /api/v1/status        -> { grid, retina, entityos, omnipool, version }
GET    /api/v1/wiki          -> { providers: [...] }
POST   /api/v1/retina        { question?: string } -> { line: string }
POST   /api/v1/pair          { pubkey: string } -> { token: string, expires: timestamp }
DELETE /api/v1/pair/:token   -> revoke
```

All endpoints require `Authorization: Bearer <capability-token>`.

### Data Flow (GRF)

```
R_t (phone message) --E_t (token verified)--> F --> R_{t+1} (reply + state delta)
```

- `R_t`: EntityOS state + session context
- `E_t`: Verified capability token + message payload
- `F`: Ground mode router (local 0.8B | tool | cloud) + GRID coordination
- Precedence: Functional turn order (journal tick), not wall-clock

### Security Invariants (ClayCode)

```clay
module smartphone_auth {
  architecture CapabilityToken {
    stateAuthority: EntityOS
    path: PhoneRequest -> VerifyToken -> Route -> GroundMode -> GRID -> EntityOS -> Reply
  }

  invariant TokenLoopbackOnly {
    // Token MUST only be accepted from loopback / LAN CIDRs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fd00::/8, ::1/128)
    ON_VIOLATION -> RejectRequest + AuditLog
  }

  invariant TokenSingleEntity {
    // Token maps to exactly ONE EntityOS identity (the local Machine God)
    ON_VIOLATION -> RevokeToken + Alert
  }

  invariant TokenShortLived {
    // TTL <= 24h, auto-rotate on use, revocable instantly from TUI
    ON_VIOLATION -> ForceReauth
  }

  invariant NoSecretsOnPhone {
    // Phone never receives: model weights, unified.db, API keys, GRID frames
    ON_VIOLATION -> AuditLog + TokenRevocation
  }
}
```

### Reuse from Inventory

- **agentic-grid**: WebSocket chat hub pattern → adapt for phone ↔ Machine God async messaging
- **entityOSv1**: Token-protected local API routes (status, J-Space) → extend for chat/retina/wiki
- **frankenstein-4.0**: Free-Mouth free-pool lane + local 0.8B mouth → phone traffic uses same lane
- **omega android / remote / handy bridges** (referenced in inventory): Study for pairing UX, then build minimal Rust version

### Phases

#### Phase 1 — Core API (Week 1)
- [ ] `src/zero/api.rs`: axum server on `127.0.0.1:8765` (configurable via `MACHINE_GOD_API_PORT`), TLS with self-signed cert for LAN
- [ ] `src/zero/auth.rs`: Ed25519 capability tokens, QR pairing, revocation list in `unified.db`
- [ ] Endpoints: `/status`, `/wiki`, `/retina`, `/chat` (ground mode only)
- [ ] Tests: token verification, loopback CIDR enforcement, token revocation, replay determinism

#### Phase 2 — Phone Client (Week 2)
- [ ] PWA (Vite + React + TypeScript) — works offline after first load, installable on iOS/Android
- [ ] QR scanner for pairing
- [ ] Chat UI with streaming replies (Server-Sent Events or WebSocket)
- [ ] Status bar (GRID | Retina | EntityOS | Omnipool) with live updates
- [ ] Settings: token management, server address, language

#### Phase 3 — Polish & Harden (Week 3)
- [ ] Background sync: phone pulls missed messages on wake
- [ ] Notification support (Web Push API via VAPID, routed through local push gateway)
- [ ] TUI integration: `/phone pair` shows QR, `/phone revoke <token>`, `/phone status`
- [ ] Documentation in `docs/zero/smartphone.md` (this file) with screenshots

### Measurement Gates

| Gate | Metric | Target | Status |
|------|--------|--------|--------|
| API latency (local) | p95 /chat | < 200 ms (ground mode) | PLANNED |
| Token verify | p99 | < 5 ms | PLANNED |
| Pairing flow | User time | < 30 s | PLANNED |
| Battery impact (phone) | 24h idle | < 2% | PLANNED |
| Replay determinism | 1000 permutations | Identical state hash | PLANNED |

### Unknowns

- iOS PWA push limitations (may need TestFlight / App Store build) — UNKNOWN
- Tailscale vs. WireGuard vs. plain LAN — pick one default, document others — UNKNOWN
- Whether `agentic-grid` WebSocket hub can be embedded as a library or must run as separate process — UNKNOWN

### Next Step
Implement `src/zero/api.rs` + `src/zero/auth.rs` with unit tests. Then a minimal PWA that pairs and shows `/status`.
