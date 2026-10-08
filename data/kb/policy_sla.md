---
doc_key: policy_sla
doc_type: policy
title: "Service Level Agreements"
product_areas:
  - platform_availability
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: admin
review_due_at: "2026-09-29"
effective_from: "2026-07-01"
effective_to: null
---

# Service Level Agreements

## 1. Purpose

This document defines the service level agreements (SLAs) governing platform uptime and support response times for each Taskmoor subscription tier. It is the sole authoritative source for all timing commitments made to customers.

## 2. Uptime Commitments

Uptime is measured as the percentage of total minutes in a calendar month during which the Taskmoor production platform is available and materially functional, excluding scheduled maintenance windows announced at least 48 hours in advance.

| Plan       | Monthly Uptime Commitment |
|------------|---------------------------|
| Free       | No uptime SLA             |
| Starter    | 99.5%                     |
| Business   | 99.9%                     |
| Enterprise | 99.95%                    |

## 3. Support Response Time Targets

Response time targets apply to Business and Enterprise plans only. Free and Starter plans receive support on a best-effort or standard-queue basis, respectively, without contractual response time guarantees.

The following table states the First Response Time (FRT) and Resolution Time targets for the Business plan. Enterprise targets are calculated by applying the Enterprise FRT multiplier of 0.5x to the Business base values.

### 3.1 Business Plan Response Targets (1x FRT Multiplier)

| Priority | First Response Time | Resolution Target |
|----------|--------------------:|------------------:|
| Urgent   | 1 hour              | 8 hours           |
| High     | 4 hours             | 1 business day    |
| Normal   | 1 business day      | 3 business days   |
| Low      | 2 business days     | 5 business days   |

### 3.2 Enterprise Plan Response Targets (0.5x FRT Multiplier)

| Priority | First Response Time | Resolution Target  |
|----------|--------------------:|-------------------:|
| Urgent   | 30 minutes          | 4 hours            |
| High     | 2 hours             | 4 business hours   |
| Normal   | 4 business hours    | 1.5 business days  |
| Low      | 1 business day      | 2.5 business days  |

## 4. Definitions

- **First Response Time (FRT):** The elapsed time between ticket creation and the first substantive response from a Taskmoor support agent, excluding automated acknowledgments.
- **Resolution Target:** The elapsed time between ticket creation and the point at which the issue is resolved or a viable workaround is provided.
- **Business Day (BD):** Monday through Friday, 09:00-18:00 in the customer's designated support region, excluding regional public holidays.
- **Business Hours:** Clock hours that fall within business days as defined above.

## 5. Enterprise Service Credits

Enterprise customers whose monthly uptime falls below the 99.95% commitment are eligible for service credits as follows:

| Monthly Uptime        | Service Credit (% of Monthly Fee) |
|-----------------------|----------------------------------:|
| 99.00% - 99.94%      | 10%                               |
| 95.00% - 98.99%      | 25%                               |
| Below 95.00%          | 50%                               |

Service credits must be requested in writing within 30 days of the end of the affected month. Credits are applied to the next invoice and do not exceed 50% of the monthly fee for the affected service. Service credits are the sole and exclusive remedy for failure to meet the uptime SLA.

## 6. Exclusions

SLA commitments do not apply to: (a) features labeled as beta or preview; (b) outages caused by customer-side network or infrastructure failures; (c) force majeure events; (d) abuse or misuse of the platform in violation of the Acceptable Use Policy; or (e) scheduled maintenance windows.

## 7. SLA Reporting

Enterprise customers may request monthly SLA compliance reports from their named Customer Success Manager. Business customers may view uptime statistics on the Taskmoor status page.
