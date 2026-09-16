# Quickmeal WhatsApp → Meta CAPI Closing Attribution System

**Document type:** Master Implementation Brief\
**Purpose:** Technical and product specification for an AI coding agent\
**Primary goal:** Make Meta able to distinguish Click-to-WhatsApp leads
that become paid purchases from leads that do not close, while giving
Quickmeal a live operational dashboard\
**Implementation principle:** Minimal, observable, reliable, modular, no
unnecessary CRM/ERP scope

------------------------------------------------------------------------

# 1. Project Objective

Build a small internal system that connects Quickmeal's WhatsApp lead
flow with Meta's Conversions API for Business Messaging

The system must:

1.  Receive inbound WhatsApp webhook events
2.  Identify leads originating from Meta Click-to-WhatsApp ads
3.  Capture and preserve Meta attribution identifiers, especially
    `ctwa_clid` when supplied
4.  Store lead and attribution data safely
5.  Show leads and their status in a live dashboard
6.  Allow an operator to mark a lead/order as `PAID` or `LOST`
7.  Record purchase value and currency
8.  Send a `Purchase` conversion back to Meta when a valid attributed
    order is paid
9.  Prevent duplicate Purchase events
10. Log webhook, attribution, conversion, retry, and error activity
11. Show whether Meta CAPI delivery succeeded or failed
12. Keep Meta credentials and access tokens server-side only

This is not intended to become a full CRM, ERP, accounting system,
WhatsApp inbox replacement, or order-management suite

------------------------------------------------------------------------

# 2. Business Outcome

Current condition:

``` text
Meta Ads
→ Customer clicks WhatsApp
→ Customer chats
→ Quickmeal handles the conversation manually
→ Customer may or may not purchase
→ Meta has incomplete downstream closing feedback
```

Target condition:

``` text
Meta Ads
→ Customer clicks WhatsApp
→ Customer sends message
→ WhatsApp webhook receives message + attribution context
→ System stores lead + ctwa_clid
→ Lead appears in dashboard
→ Quickmeal handles chat normally in WhatsApp Business App
→ Customer pays
→ Operator marks order PAID
→ Backend sends Purchase event to Meta CAPI
→ Meta receives closing feedback
→ Dashboard shows CAPI delivery status
```

For non-closing leads:

``` text
Lead
→ Operator marks LOST
→ No Purchase event is sent
```

------------------------------------------------------------------------

# 3. Non-Goals

Do not build the following in the initial version:

-   Full CRM
-   Full WhatsApp chat inbox
-   ERP integration
-   Accounting
-   Inventory
-   Payment gateway
-   Customer loyalty
-   Marketing automation
-   AI chatbot
-   Broadcast messaging
-   Complex campaign analytics
-   Multi-company architecture
-   Mobile application

Design the backend modularly so these can be added later without
rewriting the attribution core

------------------------------------------------------------------------

# 4. Required External Platforms

The system is expected to integrate with:

-   WhatsApp Business App currently used by Quickmeal
-   WhatsApp Business Platform / Cloud API using supported coexistence
    onboarding
-   Meta Developer App
-   Meta Graph API
-   Meta Conversions API for Business Messaging
-   Quickmeal database
-   Quickmeal internal dashboard

Before implementing any API contract, the coding agent must verify the
current Meta API version and official documentation rather than
hardcoding assumptions from this brief

Official references:

-   https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
-   https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
-   https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens
-   https://developers.facebook.com/documentation/business-messaging/whatsapp/permissions
-   https://developers.facebook.com/documentation/ads-commerce/conversions-api/business-messaging
-   https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/

------------------------------------------------------------------------

# 5. System Architecture

Recommended minimal architecture:

``` text
                         ┌──────────────────────┐
                         │      Meta Ads        │
                         └──────────┬───────────┘
                                    │ Click to WhatsApp
                                    ▼
                         ┌──────────────────────┐
                         │ WhatsApp Business    │
                         │ App + Platform       │
                         └──────────┬───────────┘
                                    │ Webhook
                                    ▼
┌───────────────────┐    ┌──────────────────────┐
│ Internal Dashboard│◄──►│   Backend API        │
└───────────────────┘    │                      │
                         │ Webhook processing   │
                         │ Lead service         │
                         │ Attribution service  │
                         │ Conversion service   │
                         │ Retry worker         │
                         └──────────┬───────────┘
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
                 ┌────────────────┐   ┌─────────────────┐
                 │    Database    │   │ Meta CAPI       │
                 └────────────────┘   └─────────────────┘
```

The frontend must never call Meta CAPI directly

All secrets and CAPI operations must live in the backend

------------------------------------------------------------------------

# 6. Core Domain Model

The implementation should separate these concepts:

## Lead

A WhatsApp contact/conversation entering the system

## Attribution Touch

A specific advertising attribution context associated with a lead, such
as a `ctwa_clid`

A lead may have more than one advertising touch over time

## Order

A commercial transaction associated with a lead

One lead may create multiple orders

## Conversion Event

The event sent to Meta for a particular paid order

One paid order must map to no more than one successful Meta Purchase
event

This separation is important

Do not model `phone_number = one order`

------------------------------------------------------------------------

# 7. Recommended Database Schema

The coding agent may adapt field types to the chosen database, but must
preserve the concepts and constraints below

## `leads`

``` text
id
wa_id
phone_number
customer_name
source
status
first_message_at
last_message_at
created_at
updated_at
```

Recommended `source` values:

``` text
META_AD
ORGANIC
UNKNOWN
```

Recommended lead `status` values:

``` text
NEW
CONTACTED
QUALIFIED
ORDER_PENDING
PAID
LOST
```

`PAID` at lead level is only a convenience summary

Order status remains the source of truth for purchases

------------------------------------------------------------------------

## `attribution_touches`

``` text
id
lead_id
ctwa_clid
source_id
source_type
source_url
headline
body
media_type
raw_referral_json
received_at
created_at
```

Requirements:

-   Store `ctwa_clid` exactly as received
-   Do not hash or modify it unless current Meta documentation
    explicitly requires otherwise
-   Preserve the raw referral/context object for debugging
-   Support multiple attribution touches per lead
-   Do not overwrite historical attribution when the same customer
    returns through another ad

------------------------------------------------------------------------

## `whatsapp_messages`

This table can remain lightweight and is primarily for webhook
traceability, not for recreating a full WhatsApp inbox

``` text
id
lead_id
wa_message_id
direction
message_type
received_at
raw_payload_json
created_at
```

`wa_message_id` must be unique when available to support webhook
idempotency

------------------------------------------------------------------------

## `orders`

``` text
id
order_number
lead_id
status
value
currency
paid_at
lost_at
notes
created_by
created_at
updated_at
```

Recommended status:

``` text
PENDING
PAID
LOST
CANCELLED
REFUNDED
```

Initial currency:

``` text
IDR
```

Never store Rupiah purchase values as formatted strings such as
`Rp149.900`

Use an integer or appropriate numeric representation, for example:

``` text
149900
```

------------------------------------------------------------------------

## `conversion_events`

``` text
id
order_id
platform
event_name
event_id
ctwa_clid
event_time
value
currency
status
attempt_count
last_attempt_at
sent_at
http_status
provider_response_json
last_error
created_at
updated_at
```

Recommended status:

``` text
PENDING
SENDING
SUCCESS
FAILED
RETRY_SCHEDULED
NOT_ATTRIBUTABLE
```

Database constraints:

-   `event_id` must be unique
-   A unique constraint must prevent more than one Meta `Purchase`
    conversion record for the same order
-   A successful event must never be resent automatically

------------------------------------------------------------------------

## `webhook_events`

``` text
id
provider
external_event_key
event_type
payload_json
status
processed_at
error
created_at
```

Use this for observability and deduplication

------------------------------------------------------------------------

## `audit_logs`

``` text
id
actor_id
action
entity_type
entity_id
before_json
after_json
created_at
```

Critical actions to audit:

-   Mark Paid
-   Mark Lost
-   Edit transaction value
-   Retry CAPI
-   Change attribution manually
-   Cancel/refund state changes

------------------------------------------------------------------------

# 8. WhatsApp Webhook Requirements

The backend must expose endpoints for Meta webhook verification and
webhook ingestion

Example conceptual routes:

``` text
GET  /api/webhooks/whatsapp
POST /api/webhooks/whatsapp
```

Exact implementation must follow the current official Meta webhook
specification

## Webhook processing rules

When an inbound event arrives:

1.  Validate that the request is authentic according to current Meta
    requirements
2.  Store the webhook event or enough information to debug it
3.  Detect duplicate delivery
4.  Extract WhatsApp user/contact identifier
5.  Extract message ID
6.  Extract timestamp
7.  Extract inbound message metadata
8.  Inspect referral/context advertising data
9.  Extract `ctwa_clid` when present
10. Create or update the lead
11. Create a new attribution touch when a new valid advertising touch
    exists
12. Store the lightweight message record
13. Return an acknowledgement quickly
14. Perform non-essential processing asynchronously where practical

Webhook processing must be idempotent

Meta may retry webhook delivery

A repeated webhook must not create duplicate leads, messages,
attribution touches, orders, or conversions

------------------------------------------------------------------------

# 9. Attribution Rules

Attribution is the most important logic in this project

## Meta Ad Lead

If the inbound Click-to-WhatsApp context contains a valid `ctwa_clid`:

``` text
source = META_AD
```

Store the identifier immediately

## Organic Lead

If no ad attribution exists:

``` text
source = ORGANIC
```

Do not invent a `ctwa_clid`

## Unknown

Use `UNKNOWN` only when the system genuinely cannot determine the source

## Returning Customer

A phone number is not sufficient to decide which ad generated a later
order

Store attribution as individual touches

For V1, when an operator creates or marks an order paid, the backend
should automatically propose the most recent eligible Meta attribution
touch for that lead

The dashboard must show which attribution touch will be used before the
Purchase event is sent

The implementation must keep this logic isolated in an
`AttributionService` so the rule can later be changed without rewriting
the order system

Do not silently attribute an organic purchase to an old ad click when
the current Meta eligibility/attribution requirements do not permit it

If there is no eligible `ctwa_clid`, mark the conversion:

``` text
NOT_ATTRIBUTABLE
```

The order can still be `PAID`

The dashboard must distinguish:

``` text
Paid Order
```

from:

``` text
Paid Order Successfully Attributed to Meta
```

------------------------------------------------------------------------

# 10. Operator Workflow

Quickmeal continues handling conversations through the existing WhatsApp
Business App

The dashboard is for attribution and closing monitoring

## Basic workflow

``` text
Lead arrives
→ Lead automatically appears in dashboard
→ Operator handles conversation in WhatsApp
→ Customer pays
→ Operator opens lead/order in dashboard
→ Clicks MARK AS PAID
→ Enters/confirms purchase information
→ Backend creates paid order
→ Backend resolves eligible attribution
→ Backend creates conversion event
→ Backend sends Purchase to Meta
→ Dashboard shows result
```

For a non-closing lead:

``` text
Lead
→ MARK AS LOST
→ Optional lost reason
→ No Purchase sent
```

------------------------------------------------------------------------

# 11. Mark as Paid UI

The `MARK AS PAID` action must open a confirmation form

Required fields:

``` text
Order Number
Purchase Value
Currency
Paid Date/Time
```

Default:

``` text
Currency = IDR
Paid Date/Time = current time
```

Display before confirmation:

``` text
Customer
Phone
Lead Source
ctwa_clid availability
Selected attribution touch
Purchase Value
```

The operator must be able to see whether the order is attributable
before confirming

After confirmation:

-   Save the order first
-   Commit database transaction
-   Queue conversion delivery
-   Do not block the UI waiting indefinitely for Meta
-   Show conversion as `PENDING` until delivery result is known

------------------------------------------------------------------------

# 12. Meta CAPI Purchase Event

Use Meta Conversions API for Business Messaging according to the current
official API version

Conceptual event:

``` json
{
  "event_name": "Purchase",
  "event_time": "<unix_timestamp>",
  "event_id": "<stable_unique_order_event_id>",
  "action_source": "business_messaging",
  "messaging_channel": "whatsapp",
  "user_data": {
    "ctwa_clid": "<stored_click_identifier>"
  },
  "custom_data": {
    "value": 149900,
    "currency": "IDR"
  }
}
```

Important:

-   Treat the payload above as conceptual, not a substitute for current
    Meta documentation
-   Verify endpoint path, API version, required fields, permission
    scopes, and any messaging outcome fields before implementation
-   `event_id` must be stable and unique
-   `event_time` must represent the actual business event time as
    required by Meta
-   `ctwa_clid` must come from the original WhatsApp attribution data
-   Never fabricate attribution identifiers
-   Store the exact outbound payload and Meta response in secure logs
    with secrets redacted

------------------------------------------------------------------------

# 13. Idempotency and Duplicate Prevention

This is a hard requirement

The system must guarantee:

``` text
ONE ORDER
=
MAXIMUM ONE SUCCESSFUL META PURCHASE EVENT
```

Recommended strategy:

1.  Generate deterministic/stable `event_id` from the order identity,
    for example `quickmeal_purchase_<order_uuid>`
2.  Enforce a unique database constraint on
    `order_id + platform + event_name`
3.  Lock or atomically transition conversion status before sending
4.  Ignore repeated `MARK AS PAID` requests once the order is already
    paid
5.  Never automatically resend a `SUCCESS` conversion
6.  Webhook duplicate handling must use unique external message/event
    identifiers
7.  Retry must reuse the same `event_id`

Do not rely only on frontend button disabling

Idempotency must be enforced server-side and at database level

------------------------------------------------------------------------

# 14. Retry Strategy

Transient API failures must not lose conversions

Suggested initial retry schedule:

``` text
Attempt 1: immediately
Attempt 2: +1 minute
Attempt 3: +5 minutes
Attempt 4: +30 minutes
Attempt 5: +2 hours
```

The coding agent may improve the schedule with exponential backoff and
jitter

Retry only failures considered retryable

Examples:

``` text
Network timeout
HTTP 429
Temporary 5xx
```

Do not blindly retry permanent configuration or validation failures

Examples:

``` text
Invalid token
Missing required field
Invalid ctwa_clid
Permission denied
Malformed payload
```

Permanent failures must be visible in the dashboard with a useful error
message and manual retry option after correction

------------------------------------------------------------------------

# 15. Dashboard Requirements

The dashboard must allow Quickmeal to monitor both commercial
performance and integration health

## Overview Cards

Minimum:

``` text
Total Leads
Meta Ads Leads
Organic Leads
Paid Orders
Lost Leads
Lead-to-Paid Conversion Rate
Revenue
Average Order Value
CAPI Success
CAPI Failed
CAPI Pending
Not Attributable
```

All time-based metrics should support at least:

``` text
Today
Last 7 Days
Last 30 Days
Custom Range
```

Definitions must be explicit and consistent

Example:

``` text
Lead-to-Paid Conversion Rate
=
unique leads with at least one paid order
÷
eligible leads in selected period
```

Do not mix message count with lead count

------------------------------------------------------------------------

# 16. Leads Table

Minimum columns:

  Column          Purpose
  --------------- ----------------------------------
  Customer        Display name
  Phone           WhatsApp number
  First Contact   First inbound timestamp
  Source          Meta Ads / Organic / Unknown
  Attribution     ctwa_clid available or not
  Lead Status     Current lead state
  Orders          Number of orders
  Paid Value      Total paid value
  CAPI            Success / Failed / Pending / N/A
  Action          Open detail

Filters:

-   Date
-   Source
-   Lead status
-   CAPI status
-   Paid / unpaid
-   Search by name or phone

------------------------------------------------------------------------

# 17. Lead Detail Page

Show:

## Customer

``` text
Name
Phone
WA ID
First Contact
Last Contact
Source
```

## Attribution

Show all known attribution touches chronologically

``` text
Received At
ctwa_clid
Source ID
Headline
Source Type
Eligibility/selected state
```

Do not hide the raw identifier from an authorized admin, but do not
expose secrets

## Orders

``` text
Order Number
Value
Currency
Status
Paid At
CAPI Status
```

## Technical Activity

``` text
Webhook received
Lead created
Attribution stored
Order marked paid
CAPI queued
CAPI attempt
Meta response
Retry
Success/failure
```

## Actions

``` text
MARK AS PAID
MARK AS LOST
RETRY CAPI
```

Actions must respect current state and permissions

------------------------------------------------------------------------

# 18. Integration Health Page

Create a dedicated technical monitoring area

Minimum health indicators:

``` text
WhatsApp Webhook: Healthy / Error
Last Webhook Received
Meta CAPI: Healthy / Error
Last Successful Purchase Event
Failed Events
Pending Retries
Token/Permission Problem
Database Health
Worker/Queue Health
```

This page exists so an operator can immediately determine whether the
system is functioning

Do not expose raw access tokens

------------------------------------------------------------------------

# 19. Logs and Observability

Every critical step must be observable

Use structured logs

Each request/event should carry correlation identifiers where possible:

``` text
lead_id
order_id
conversion_event_id
wa_message_id
```

Log:

-   webhook received
-   webhook validation
-   lead create/update
-   attribution capture
-   order status transition
-   CAPI request attempt
-   HTTP result
-   retry scheduling
-   final success
-   final failure

Redact:

-   access tokens
-   app secrets
-   authentication cookies
-   unnecessary personal data

Do not make raw logs the only monitoring interface

Surface actionable states in the dashboard

------------------------------------------------------------------------

# 20. Security Requirements

Hard requirements:

1.  Meta access token must never be sent to the browser
2.  Meta App Secret must remain server-side
3.  Secrets must use environment variables or a proper secret manager
4.  Dashboard requires authentication
5.  Sensitive mutation endpoints require authorization
6.  Validate webhook authenticity using Meta's current official
    mechanism
7.  Use HTTPS in production
8.  Apply server-side input validation
9.  Apply rate limiting where appropriate
10. Use parameterized queries / ORM protections
11. Maintain audit logs for commercial state changes
12. Avoid logging full secrets
13. Restrict database permissions
14. Use CSRF protection where applicable to the selected framework
15. Never trust status/value supplied only by the frontend

------------------------------------------------------------------------

# 21. Environment Variables

Exact names may be adapted to the stack

Example:

``` env
APP_ENV=
APP_URL=
DATABASE_URL=

META_APP_ID=
META_APP_SECRET=
META_BUSINESS_ID=
META_WABA_ID=
META_WHATSAPP_PHONE_NUMBER_ID=
META_ACCESS_TOKEN=
META_GRAPH_API_VERSION=

WHATSAPP_VERIFY_TOKEN=

SESSION_SECRET=
ENCRYPTION_KEY=

QUEUE_URL=
```

Rules:

-   Commit `.env.example`
-   Never commit `.env`
-   Never hardcode production secrets
-   Validate required environment variables at application startup

------------------------------------------------------------------------

# 22. Suggested Backend Modules

Keep business logic separated

``` text
AuthModule
LeadModule
WhatsAppWebhookModule
AttributionModule
OrderModule
ConversionModule
MetaCapiClient
RetryWorker
AuditModule
DashboardMetricsModule
HealthModule
```

Important separation:

`MetaCapiClient` handles Meta HTTP communication

`ConversionService` decides whether and when an event should be sent

`AttributionService` decides which attribution touch is eligible

Do not put all logic directly inside webhook controllers or route
handlers

------------------------------------------------------------------------

# 23. API Surface

Illustrative internal API only

``` text
GET    /api/dashboard/summary
GET    /api/leads
GET    /api/leads/:id
PATCH  /api/leads/:id/status

POST   /api/leads/:id/orders
POST   /api/orders/:id/mark-paid
POST   /api/orders/:id/mark-lost

GET    /api/conversions
POST   /api/conversions/:id/retry

GET    /api/health/integrations

GET    /api/webhooks/whatsapp
POST   /api/webhooks/whatsapp
```

The coding agent may adapt REST to the existing stack, but the business
capabilities must remain

------------------------------------------------------------------------

# 24. Transactional Rules

When marking an order paid:

1.  Validate user authorization
2.  Validate order state
3.  Validate amount and currency
4.  Persist `PAID` state and `paid_at`
5.  Resolve attribution
6.  Create conversion record atomically if attributable
7.  Commit
8.  Queue CAPI delivery
9.  Return current order/conversion state to UI

Do not call Meta before the paid order has been safely persisted

If Meta fails, the paid order must remain paid

CAPI failure must never roll back a legitimate business transaction

------------------------------------------------------------------------

# 25. Handling Special Cases

## Missing `ctwa_clid`

Order may still be marked `PAID`

Conversion becomes:

``` text
NOT_ATTRIBUTABLE
```

Do not invent an ID

## Organic Customer

Order can be paid and counted in Quickmeal revenue

Do not falsely claim it as Meta-attributed

## Same Customer, Multiple Orders

Create separate order records

Each order gets its own stable Purchase `event_id`

Attribution eligibility must be resolved independently for each order

## Same Customer Clicks Multiple Ads

Preserve all touches

Do not overwrite previous attribution

Use the current V1 attribution rule through `AttributionService`

## Duplicate Webhook

Acknowledge safely

Do not duplicate entities

## Operator Clicks Paid Twice

Return existing paid state

Do not create a second Purchase event

## Meta API Down

Keep conversion pending/failed as appropriate

Retry according to policy

## Token Expired or Permission Revoked

Stop futile automatic retries after classifying the error as
permanent/configuration-related

Show a high-visibility integration error

## Refund

V1 must at minimum allow the order to be marked `REFUNDED` for internal
reporting

Do not invent a Meta refund/reversal event behavior

If downstream refund reporting is desired, verify current Meta
documentation before implementing it

------------------------------------------------------------------------

# 26. Testing Requirements

Automated tests are required for core business logic

## Unit Tests

At minimum:

-   attribution selection
-   paid-state transition
-   duplicate paid request
-   conversion idempotency
-   retry classification
-   currency/value validation

## Integration Tests

At minimum:

### Test A --- Meta Ad Lead

``` text
Webhook with ctwa_clid
→ lead created
→ attribution created
```

### Test B --- Organic Lead

``` text
Webhook without ad context
→ organic lead
→ no fabricated attribution
```

### Test C --- Duplicate Webhook

``` text
Same message delivered twice
→ one message record
→ one attribution touch
```

### Test D --- Successful Purchase

``` text
Attributed lead
→ mark paid
→ one conversion created
→ CAPI mocked success
→ conversion SUCCESS
```

### Test E --- Double Paid

``` text
Mark same order paid twice
→ one conversion only
```

### Test F --- Temporary CAPI Failure

``` text
CAPI 5xx
→ retry scheduled
→ later success
→ one successful event
```

### Test G --- Permanent CAPI Failure

``` text
Invalid credential/validation error
→ no endless retry
→ dashboard shows failure
```

### Test H --- Paid Organic Order

``` text
Organic lead
→ paid order
→ revenue counted
→ NOT_ATTRIBUTABLE
→ no fake Meta Purchase
```

------------------------------------------------------------------------

# 27. Real End-to-End Acceptance Test

The system is not production-ready until this test passes using a real
controlled Meta Click-to-WhatsApp flow

``` text
1. Click a real Quickmeal Click-to-WhatsApp ad
2. Send a WhatsApp message
3. Verify webhook reception
4. Verify lead appears in dashboard
5. Verify attribution identifier is stored
6. Create/mark order PAID with a controlled value
7. Verify exactly one Purchase event is generated
8. Verify Meta endpoint accepts the event
9. Verify dashboard changes to SUCCESS
10. Verify event is visible in the appropriate Meta diagnostics/event tooling
11. Repeat webhook or Paid action
12. Confirm no duplicate Purchase is created
```

Do not claim completion based only on mocked API tests

------------------------------------------------------------------------

# 28. Development Phases

The coding AI should work in phases and keep the application runnable
after every phase

## Phase 1 --- Foundation

Build:

-   project skeleton
-   configuration
-   database
-   migrations
-   authentication
-   base layout
-   health endpoint
-   logging

Deliverable:

``` text
Application runs
Database connects
Admin can log in
```

## Phase 2 --- Lead and Dashboard Base

Build:

-   lead schema
-   attribution schema
-   order schema
-   conversion schema
-   overview dashboard
-   leads table
-   lead detail

Use seeded/mock data initially

Deliverable:

``` text
Quickmeal can inspect the intended operational UI before live Meta integration
```

## Phase 3 --- WhatsApp Webhook

Build:

-   verification endpoint
-   webhook ingestion
-   validation
-   event logging
-   duplicate protection
-   lead creation
-   message metadata storage

Deliverable:

``` text
Real WhatsApp inbound webhook can create/update a lead
```

## Phase 4 --- Attribution Capture

Build:

-   parse ad/referral context
-   capture `ctwa_clid`
-   attribution history
-   source classification
-   dashboard visibility

Deliverable:

``` text
A Click-to-WhatsApp lead can be distinguished from an organic lead
```

## Phase 5 --- Closing Workflow

Build:

-   order creation
-   Mark Paid
-   Mark Lost
-   transaction value
-   audit logs
-   attribution preview

Deliverable:

``` text
Operator can record which leads actually close
```

## Phase 6 --- Meta CAPI

Build:

-   Meta CAPI client
-   Purchase payload
-   event IDs
-   conversion records
-   secure token handling
-   response logging

Deliverable:

``` text
Attributed paid order can send one Purchase event to Meta
```

## Phase 7 --- Reliability

Build:

-   retry queue
-   error classification
-   manual retry
-   integration health
-   alerts/status
-   idempotency hardening

Deliverable:

``` text
Temporary integration failures do not silently lose conversions
```

## Phase 8 --- Testing and Production Hardening

Build/run:

-   unit tests
-   integration tests
-   real end-to-end test
-   production environment
-   HTTPS
-   backups
-   monitoring
-   deployment documentation

Deliverable:

``` text
Production-ready system with verified real Meta event delivery
```

------------------------------------------------------------------------

# 29. Current External Setup Status

At the time this brief was created:

``` text
WhatsApp Business App in use                 DONE
Current WhatsApp condition audited           DONE
Business Platform coexistence connection     NOT YET DONE
Meta Developer App                           NOT YET DONE
WhatsApp webhook                             NOT YET DONE
ctwa_clid capture                            NOT YET DONE
Lead database                                NOT YET DONE
Closing dashboard                            NOT YET DONE
Meta CAPI integration                        NOT YET DONE
End-to-end Meta test                         NOT YET DONE
Production activation                        NOT YET DONE
```

The coding AI may build Phases 1 and 2 in parallel while the human
completes Meta/WhatsApp external configuration

Do not fabricate credentials, WABA IDs, phone number IDs, app IDs, or
access tokens

Use placeholders until real values are supplied

------------------------------------------------------------------------

# 30. Milestones to Final Business Goal

``` text
M1  Audit existing WhatsApp                  DONE
M2  Connect WhatsApp Business Platform       PENDING
M3  Configure Meta Developer App             PENDING
M4  Receive WhatsApp webhook                 PENDING
M5  Capture ctwa_clid                        PENDING
M6  Persist leads + attribution              PENDING
M7  Record closing / Paid / Lost             PENDING
M8  Send Purchase through Meta CAPI          PENDING
M9  Pass real end-to-end test                PENDING
M10 Go live                                  PENDING
M11 Use verified downstream signal in
    Meta campaign optimization where
    supported/configured                     PENDING
```

M10 means Meta is receiving reliable closing feedback

M11 is a separate advertising configuration/optimization milestone and
must not be falsely considered complete merely because CAPI events are
being sent

------------------------------------------------------------------------

# 31. Definition of Done

The system is considered functionally complete only when all statements
below are true:

-   A real Click-to-WhatsApp customer can enter through an ad
-   The inbound event reaches the backend
-   The lead appears automatically in the dashboard
-   The system preserves the relevant ad attribution identifier
-   Organic and Meta-ad leads are distinguishable
-   An operator can record a paid order
-   Purchase value is stored accurately
-   An eligible paid order generates a Meta Purchase event
-   The event contains the correct attribution identifier
-   Meta accepts the event
-   Delivery status is visible in the dashboard
-   Failed delivery is visible and actionable
-   Temporary failures can retry safely
-   Duplicate webhooks do not duplicate leads/conversions
-   Repeated Paid actions do not duplicate Purchase events
-   Paid organic orders remain valid internal revenue without false Meta
    attribution
-   Credentials remain server-side
-   Critical business changes are audited
-   Real end-to-end testing has passed

Final acceptance path:

``` text
REAL META AD
→ WHATSAPP MESSAGE
→ WEBHOOK
→ LEAD IN DASHBOARD
→ ctwa_clid STORED
→ MARK AS PAID Rp149.900
→ PURCHASE EVENT CREATED
→ META CAPI
→ META ACCEPTED
→ DASHBOARD = SUCCESS
```

------------------------------------------------------------------------

# 32. Instructions to the Coding AI

Treat this document as the product and technical specification

Before writing integration code:

1.  Inspect the existing repository and stack
2.  Do not replace working architecture without a clear reason
3.  Verify current official Meta documentation and API version
4.  Identify any assumptions that require real Meta credentials or
    external setup
5.  Build external integrations behind clean interfaces so mock
    implementations can be used during development
6.  Build Phases 1 and 2 without waiting for Meta credentials
7.  Do not fabricate successful integration results
8.  Do not mark a milestone complete until its acceptance criteria
    actually pass
9.  Keep migrations reversible and committed
10. Keep secrets out of source control
11. Add tests for critical attribution and idempotency logic
12. Keep the dashboard simple and operationally useful
13. Prefer reliable explicit behavior over clever automation
14. Preserve raw Meta referral/context payloads needed for debugging,
    while applying appropriate access control and retention
15. Document setup commands, environment variables, migration commands,
    test commands, and deployment steps in the repository README

When Meta configuration is not yet available, create adapters/interfaces
and mock fixtures based on documented payloads, then wait for real
credentials/data for final integration testing

------------------------------------------------------------------------

# 33. Key Engineering Principle

The core invariant of this system is:

``` text
The system must never claim that Meta generated a purchase unless a legitimate
WhatsApp advertising attribution identifier exists and the business has
actually marked the corresponding order as paid
```

The second invariant is:

``` text
One paid order must never create more than one successful Meta Purchase event
```

Everything else is secondary to attribution integrity, transaction
integrity, observability, and security
