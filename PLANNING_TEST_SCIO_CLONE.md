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
|  | Offline Cache (IndexedDB / SQLite) | Local Cron Scheduler | Telemetry Engine |  |
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

### The Discovery: Offline Pre-Staging & Atomic Playlist Swapping
During hands-on exploration of `app.optisigns.com` and testing screen pairing behavior, I expected the player to behave like a standard rich media streaming client: when a playlist changes or a schedule triggers, the player requests media URLs on-demand from the CDN over the active network connection.

However, observing player network tabs and inspecting edge disconnection behavior revealed a critical reality: **OptiSigns players operate on an aggressive Offline-First Pre-Staging Model**. 
1. When a new playlist or scheduled item is deployed, the player **does not switch immediately**.
2. It silently downloads the entire bundle of assets (videos, images, font files, and HTML widget bundles) into local storage (IndexedDB/CacheStorage for Web, Local Flash for Android) and performs a checksum verification.
3. Only when 100% of the media assets are confirmed verified locally does the player atomically flip the active playback pointer.
4. If internet connectivity drops entirely for hours or days, the screen continues its precise multi-zone scheduled playback loop without dropping a single frame or ever exposing a "Network Error / Reconnecting" screen to retail customers.

### Architectural & Planning Pivot:
* **Initial Plan Assumption**: The Player Agent was budgeted as a straightforward React SPA iframe wrapper streaming assets directly from CDN URLs, estimated at **4 weeks** in Phase 2.
* **Impact of the Discovery**:
  1. **Architecture Pivot**: The Player Core cannot be a thin streaming web view. It requires:
     - An **Offline Asset Cache Manager** with persistent chunked downloading and SHA-256 integrity verification.
     - A **Local Time-Engine**: A standalone edge scheduling state machine that evaluates cron rules against the device's local clock rather than relying on server timing.
     - An **Atomic Surface Swap**: Dual-buffer rendering (Background Canvas pre-warms video decode while Foreground Canvas plays) to guarantee zero-gap transitions.
  2. **Roadmap & Resource Impact**:
     - Increased Player Core effort from **4 weeks to 7 weeks**.
     - Elevated Player Core development to the **Critical Path** alongside the Backend API starting in Milestone 1.
     - Deprioritized complex cloud transitions and social media app integrations in MVP to guarantee **100% offline playback resilience**.

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
• Offline-First Edge Player Core (IndexedDB, pre-fetch worker, atomic swap)

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
| **M2** | Playlist, Schedule & Offline Player | Multi-zone layout, offline pre-fetch cache, local scheduler | 8 Weeks | M1 |
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
  - Offline cache manager, dual-buffer video compositor, Android/FireOS APK wrapper.

---

## 6. Scope Boundaries (In-Scope vs. Explicitly Deferred)

### Strictly In-Scope (MVP Delivery)
- Multi-tenant Organization & Team management with Role-Based Access Control (Admin, Editor, Viewer).
- 6-digit screen pairing code with automatic reconnect handshake.
- Asset library with automated transcoding for MP4, PNG, JPG, WebP.
- Multi-zone layout designer (fullscreen, 2-zone, 3-zone split).
- Dayparting & recurring scheduling engine (e.g. Breakfast Menu: 06:00–10:30, Lunch: 10:30–14:00).
- Offline-first playback engine with background asset verification.
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
