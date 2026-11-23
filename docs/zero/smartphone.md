# Smartphone Link Plan — Machine God / Zero40

Status: PLANNED.

## Goal
Connect a smartphone to the Machine God entity running locally (claude-rs + Zero + FranKenstein 3.0) so the user can:
- Send messages / prompts from the phone
- Receive responses / notifications on the phone
- See the entity's status line (GRID | Retina | EntityOS | Omnipool)
- Trigger small reflex actions (wiki lookup, Retina one-line, provider status)

## Constraints (Hard)
- **Loopback only**: The phone talks to the local machine via LAN (Tailscale / WireGuard / local Wi-Fi). No public internet exposure.
- **No secrets on the phone**: The phone holds only a revocable capability token; all keys, model weights, and unified.db stay on the host.
- **Single entity**: The phone is a *view* into the same EntityOS/GRID/Retina that the TUI uses — not a second agent.
- **Free pool only by default**: Phone traffic routes through Omnipool (local free models). Claude Code path is opt-in from the TUI.

## Architecture Sketch

```
[Phone] <-- HTTPS (TLS, loopback LAN) --> [Machine God HTTP API : 8765]
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
| Phone UI (PWA / React Native / Tauri mobile) | Reuse: `agentic-grid` chat hub pattern | PLANNED |
| Push / WebSocket for async replies | Reuse: `agentic-grid` WebSocket hub | PLANNED |
| QR code pairing (token exchange) | New | PLANNED |

## API Surface (Minimal v1)

```
POST   /api/v1/chat          { message: string, session_id?: string } -> { reply: string, session_id: string }
GET    /api/v1/status        -> { grid, retina, entityos, omnipool, version }
GET    /api/v1/wiki          -> { providers: [...] }
POST   /api/v1/retina        { question?: string } -> { line: string }
POST   /api/v1/pair          { pubkey: string } -> { token: string, expires: timestamp }
DELETE /api/v1/pair/:token   -> revoke
```

All endpoints require `Authorization: Bearer <capability-token>`.

## Data Flow (GRF)

```
R_t (phone message) --E_t (token verified)--> F --> R_{t+1} (reply + state delta)
```

- `R_t`: EntityOS state + session context
- `E_t`: Verified capability token + message payload
- `F`: Ground mode router (local 0.8B | tool | cloud) + GRID coordination
- Precedence: Functional turn order (journal tick), not wall-clock

## Security Invariants (ClayCode)

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

## Reuse from Inventory

- **agentic-grid**: WebSocket chat hub pattern → adapt for phone ↔ Machine God async messaging
- **entityOSv1**: Token-protected local API routes (status, J-Space) → extend for chat/retina/wiki
- **frankenstein-4.0**: Free-Mouth free-pool lane + local 0.8B mouth → phone traffic uses same lane
- **omega android / remote/handy bridges** (referenced in inventory): Study for pairing UX, then build minimal Rust version

## Phases

### Phase 1 — Core API (Week 1)
- [ ] `src/zero/api.rs`: axum server on 127.0.0.1:8765 (configurable via `MACHINE_GOD_API_PORT`), TLS with self-signed cert for LAN
- [ ] `src/zero/auth.rs`: Ed25519 capability tokens, QR pairing, revocation list in unified.db
- [ ] Endpoints: `/status`, `/wiki`, `/retina`, `/chat` (ground mode only)
- [ ] Tests: token verification, loopback CIDR enforcement, token revocation, replay determinism

### Phase 2 — Phone Client (Week 2)
- [ ] PWA (Vite + React + TypeScript) — works offline after first load, installable on iOS/Android
- [ ] QR scanner for pairing
- [ ] Chat UI with streaming replies (Server-Sent Events or WebSocket)
- [ ] Status bar (GRID | Retina | EntityOS | Omnipool) with live updates
- [ ] Settings: token management, server address, language

### Phase 3 — Polish & Harden (Week 3)
- [ ] Background sync: phone pulls missed messages on wake
- [ ] Notification support (Web Push API via VAPID, routed through local push gateway)
- [ ] TUI integration: `/phone pair` shows QR, `/phone revoke <token>`, `/phone status`
- [ ] Documentation in `docs/zero/smartphone.md` (this file) with screenshots

## Measurement Gates

| Gate | Metric | Target |
|------|--------|--------|
| API latency (local) | p95 /chat | < 200 ms (ground mode) |
| Token verify | p99 | < 5 ms |
| Pairing flow | User time | < 30 s |
| Battery impact (phone) | 24h idle | < 2% |
| Replay determinism | 1000 permutations | Identical state hash |

## Unknowns

- iOS PWA push limitations (may need TestFlight / App Store build)
- Tailscale vs. WireGuard vs. plain LAN — pick one default, document others
- Whether `agentic-grid` WebSocket hub can be embedded as a library or must run as separate process

## Next Step
Implement `src/zero/api.rs` + `src/zero/auth.rs` with unit tests. Then a minimal PWA that pairs and shows `/status`.
