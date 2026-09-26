# SCIO Platform Architecture & Execution Roadmap (Part 2: Planning Test)

**Target Role**: Full Stack Developer / Tech Lead  
**Candidate**: Nguyen Mau Minh Duc  
**Scope**: End-to-End Architectural Blueprint & Phased Execution Plan for Cloning SCIO (Digital Signage CMS & Edge Player Platform)

---

## 1. Executive Summary & Product Vision

**SCIO** is an enterprise-grade, cloud-native Digital Signage Management Platform. Its core mission is transforming distributed physical displays (TVs, kiosks, digital menu boards, LED walls) into intelligently orchestrated, remotely managed smart screens.

Unlike typical web CMS applications, a Digital Signage system has a dual nature:
1. **Central Cloud Control Plane**: Multi-tenant web portal for asset authoring, layout zoning, playlist orchestration, schedule management, and fleet telemetry.
2. **Distributed Edge Player Runtime**: High-reliability edge software executing on heterogeneous physical hardware (FireOS, Android, Raspberry Pi, Windows, WebOS, Tizen) under intermittent network conditions.

This plan details the technical architecture, team structure, milestone breakdown, and risk mitigation strategy required to deliver a production-ready clone from scratch within **6 months** with an agile team of **6 engineers**.

---

## 2. Core Architecture & Tech Stack Decisions

```
+-----------------------------------------------------------------------------------+
|                            CENTRAL CLOUD CONTROL PLANE                            |
|                                                                                   |
|  +--------------------+     +---------------------+     +----------------------+  |
|  | Web Portal (React) |     | REST / GraphQL API  |     | Real-time Gateway    |  |
|  | Vite + Tailwind    | <-> | NestJS / TypeScript | <-> | EMQX (MQTT Broker)   |  |
|  | Zustand + Query    |     | Modular Monolith    |     | Heartbeats & Commands|  |
|  +--------------------+     +---------------------+     +----------------------+  |
|                                        |                            |             |
|                 +----------------------+----------------------+     |             |
|                 |                      |                      |     |             |
|        +-----------------+    +------------------+    +--------------+            |
|        | PostgreSQL + PG |    | Redis Cluster    |    | AWS S3 +     |            |
|        | Relational/JSONB|    | Cache & Pub/Sub  |    | CloudFront   |            |
|        +-----------------+    +------------------+    +--------------+            |
+-----------------------------------------------------------------------------------+
                                         ^                            ^
                                         | Sync / Asset Download      | MQTT Commands
                                         v                            v
+-----------------------------------------------------------------------------------+
|                            DISTRIBUTED EDGE RUNTIMES                              |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Common Core: TypeScript/Web Components Player Engine                        |  |
|  | Device cache for downloaded files | Local scheduler | Skip live apps offline |  |
|  +-----------------------------------------------------------------------------+  |
|         |                           |                               |             |
|  +---------------+          +---------------+               +---------------+     |
|  | Android TV /  |          | PWA / WebOS / |               | Windows /     |     |
|  | Fire OS (APK) |          | Tizen Runtime |               | Linux Player  |     |
|  +---------------+          +---------------+               +---------------+     |
+-----------------------------------------------------------------------------------+
```

### 2.1 Backend: Modular Monolith (NestJS / TypeScript)
* **Decision**: Single repository modular monolith with strict domain boundaries (`iam`, `screens`, `assets`, `playlists`, `schedules`, `telemetry`), deployed on AWS ECS (Fargate).
* **Rationale**: A microservices architecture introduces severe network serialization overhead, distributed transaction complexity, and DevOps friction for a new team. A modular monolith allows maximum velocity, single-deployment simplicity, and rapid schema refactoring while preserving future extractability into microservices if specific domains (like telemetry ingestion) require isolated horizontal scaling.

### 2.2 Data Layer: PostgreSQL + Redis Cluster
* **PostgreSQL (AWS Aurora)**: Primary database. Stores relational hierarchies (Tenants, Users, Screen Groups, Permissions) and utilizes JSONB for flexible playlist item configurations and custom widget metadata.
* **Redis**: Distributed session caching, real-time rate limiting, and ephemeral player heartbeat deduplication.

### 2.3 Real-Time Device Communication: MQTT (EMQX) over WebSockets / TLS
* **Decision**: Managed MQTT Broker (EMQX Cloud) for device heartbeats, command dispatch, and screen pairing.
* **Rationale**: Standard HTTP polling at scale (e.g. 50,000 screens polling every 10 seconds = 5,000 req/sec) degrades database throughput and increases egress costs. MQTT delivers ultra-low packet overhead (2-byte header), persistent bi-directional QoS-1 delivery, and instant screen takeover capability (< 500ms latency).

### 2.4 Frontend Portal: React + Vite + TailwindCSS + Zustand + TanStack Query
* **Rationale**: Fast initial load, zero-runtime CSS footprint, predictable state management without Redux boilerplate. Interactive multi-zone canvas editor built with HTML5 Canvas / Fabric.js.

### 2.5 Asset Transcoding & CDN Pipeline
* **Storage**: AWS S3 + CloudFront CDN.
* **Transcoding Pipeline**: AWS Lambda + AWS MediaConvert triggered by S3 `ObjectCreated` events to normalize uploaded videos into standardized H.264/MP4 profiles with AAC audio, generating thumbnail previews and multi-resolution renditions automatically.

---

## 3. ⭐ Unexpected Product Finding & Architectural Pivot

> **MANDATORY SPECIFICATION REQUIREMENT**:  
> *"Somewhere in the document, tell us one thing you found in the product that you did not expect, and what it changed in your plan."*

### The Discovery: Cached files keep playing, and the offline state is hidden by default
I expected a lost connection to stop the screen or show a reconnecting error. OptiSigns documents the opposite in [What happens if the internet connection is lost?](https://support.optisigns.com/hc/en-us/articles/360016376793-What-happen-if-internet-connection-is-lost) and [Show/Hide Offline Indicator](https://support.optisigns.com/hc/en-us/articles/12947820509971-Show-Hide-Offline-Indicator-on-your-Player):

1. Pictures, videos, and documents are downloaded to the device. Playback of that cached content continues with no internet.
2. Live apps (YouTube, Vimeo, social feeds, dashboards) are skipped while the device is offline. They are not cached.
3. Portal edits made during the outage are held and applied after the player reconnects.
4. The offline indicator is off by default. Turning it on still waits about one minute, so a short blip does not flash a warning on a store screen.

A BrightSign troubleshooting note makes the storage consequence concrete: the player cache (`localStorage` on the SD card) can grow until the card is full and apps stop updating. That is a disk-management problem, not a streaming problem.

### Architectural & Planning Pivot:
* **Initial plan assumption**: the player is a thin web view that streams asset URLs from the CDN. Budgeted at **4 weeks** in Phase 2.
* **What changed**:
  1. The player has two content classes. Downloadable files go to a device cache and keep playing offline. Live apps are marked non-cacheable and are skipped, not failed, when the network is down.
  2. The schedule has to keep running on the device clock. A portal publish during an outage is a delta applied on reconnect, not a reason to blank the screen.
  3. The offline badge is an opt-in screen setting with a one-minute delay. It is not the default failure UI.
  4. Cache eviction is in the MVP. Cheap players run out of local disk (the BrightSign card-full case).
* **Roadmap impact**:
  * Player core moves from **4 weeks to 7 weeks** and starts on the critical path in Milestone 1, next to the API.
  * Native social and dashboard apps stay out of the MVP. A live app that cannot play offline is a known skip, not a blocker for the cacheable menu-board path.

---

## 4. Work Breakdown & Phased Execution Roadmap

We divide the 24-week delivery timeline into 4 distinct phases:

```
Month 1: Phase 1 - Foundation & Core CMS (Weeks 1-6)
=====================================================
• Tenant IAM, RBAC, Auth0/Cognito Integration
• Asset Upload Pipeline (S3 Presigned URLs + MediaConvert)
• PostgreSQL Schema & NestJS Modular Monolith Scaffolding
• Initial Screen Pairing Protocol (6-character code handshake)

Month 2-3: Phase 2 - Scheduling Engine & Offline Player (Weeks 7-14)
===================================================================
• Canvas Multi-Zone Layout Editor (Split-screen 2x2, 1x3, PIP)
• Playlist Sequencer (Durations, transitions, loop logic)
• Advanced Calendar Scheduling (Recurring rules, dayparting, priority overrides)
• Offline player: cache pictures/videos/documents, skip live apps, opt-in offline indicator

Month 4-5: Phase 3 - Fleet Telemetry & Multi-Platform Runtime (Weeks 15-20)
===========================================================================
• EMQX MQTT Real-time Heartbeat & Remote Command Dispatch (Reboot, Takeover)
• Telemetry Aggregation (Screenshot proof-of-play capture, online/offline status)
• Android TV / FireOS Native Shell Wrapper (Kotlin + Capacitor / WebView)
• WebOS & Tizen Browser Profile Compatibility

Month 6: Phase 4 - Enterprise Hardening & Launch (Weeks 21-24)
=============================================================
• Comprehensive E2E Testing & Chaos Testing (Random edge disconnects)
• Security Audit, Penetration Testing & SOC2 Compliance Readiness
• Production Multi-AZ Deployment on AWS Fargate & Load Testing (10k Concurrent Screens)
```

### Milestone & Effort Estimation Summary

| Phase | Milestone Name | Scope Highlights | Duration | Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **M1** | Core CMS & Pairing Handshake | Auth, Tenant DB, S3 uploads, 6-digit PIN screen pairing | 6 Weeks | None |
| **M2** | Playlist, Schedule & Offline Player | Multi-zone layout, device cache for files, skip live apps offline, local scheduler | 8 Weeks | M1 |
| **M3** | Fleet Ops & Native Runtimes | MQTT live commands, screenshot capture, Android APK | 6 Weeks | M2 |
| **M4** | Enterprise Scale & Launch | Load test 10k players, chaos resilience, security hardening | 4 Weeks | M3 |
| **Total** | **Production MVP Launch** | **Full feature parity for Core SCIO Platform** | **24 Weeks** | — |

---

## 5. Team Sizing & Resource Allocation

An agile engineering unit of **6 full-time engineers** is optimal for high velocity without communication overhead:

* **1x Lead / Principal Architect (Full Stack)**: System design, MQTT protocol, cross-team alignment, code reviews, security.
* **2x Backend Engineers (NestJS / PostgreSQL / AWS)**:
  - Backend 1: Core API, IAM, Playlist & Calendar Scheduling engine.
  - Backend 2: MQTT telemetry ingestion, asset transcoding pipeline, edge sync endpoints.
* **2x Frontend Engineers (React / Canvas)**:
  - Frontend 1: Web Portal UI, responsive dashboard, device management tables.
  - Frontend 2: Multi-zone visual canvas layout editor & playlist sequencer.
* **1x Edge / Player Specialist (TypeScript / Android / Embedded Web)**:
  - Device cache, live-vs-file playback rules, Android/FireOS APK wrapper.

---

## 6. Scope Boundaries (In-Scope vs. Explicitly Deferred)

### Strictly In-Scope (MVP Delivery)
- Multi-tenant Organization & Team management with Role-Based Access Control (Admin, Editor, Viewer).
- 6-digit screen pairing code with automatic reconnect handshake.
- Asset library with automated transcoding for MP4, PNG, JPG, WebP.
- Multi-zone layout designer (fullscreen, 2-zone, 3-zone split).
- Dayparting & recurring scheduling engine (e.g. Breakfast Menu: 06:00–10:30, Lunch: 10:30–14:00).
- Offline playback for downloaded pictures, videos, and documents. Live apps are skipped while offline. Offline indicator is opt-in.
- Real-time device status (Online, Offline, In Sync) and live screenshot capture via MQTT.
- Core hardware support: Web Player (PWA) + Android TV / Fire TV Stick (APK).

### Deliberately Deferred (Post-MVP / Phase 5+)
- **Third-Party App Ecosystem (Canva, PowerBI, Social Wall)**: Deferred. In MVP, users can embed web URLs; native OAuth app integrations add significant surface area without validating core playback stability.
- **AI Camera Audience Analytics (Demographics / Foot-traffic)**: Deferred to Phase 5.
- **Proprietary Hardware OS (Custom Linux ISO)**: Defer until standard Android hardware traction is established.

---

## 7. Risk Management & Defensive Strategy

1. **Risk: Edge Storage Exhaustion on Cheap TV Sticks (e.g. 8GB FireStick with 1.5GB free)**.  
   *Mitigation*: Implement LRU (Least Recently Used) cache pruning with a configurable disk watermark (e.g., maximum 80% storage consumption). Assets not referenced in current or upcoming schedules are purged automatically.
2. **Risk: "Thundering Herd" on Server when 10,000 screens reconnect simultaneously after outage**.  
   *Mitigation*: Exponential backoff with full jitter on edge reconnect attempts. Delta sync payload compressed with gzip and cached at CloudFront edge.
3. **Risk: Memory Leaks in 24/7 Browser Runtime**.  
   *Mitigation*: Scheduled soft-restarts of the web worker context during low-traffic night hours (e.g. 03:00 local time) if no active schedule is displaying.

---
*Authored for OptiSigns / AlphaSphere Technical Evaluation.*
