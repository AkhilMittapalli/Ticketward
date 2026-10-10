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

The Business plan uses a 1x FRT multiplier; Enterprise applies a 0.5x multiplier to the Business base, halving the guaranteed first-response window for every severity level.

### 3.1 Consolidated Response Targets

| Severity | Business FRT | Enterprise FRT | Business Resolution | Enterprise Resolution |
|----------|-------------:|---------------:|--------------------:|----------------------:|
| Urgent   | 60 min       | 30 min         | 8 h                | 4 h                   |
| High     | 4 h          | 2 h            | 1 BD               | 4 business hours      |
| Normal   | 1 BD         | 4 business hrs | 3 BD                | 1.5 BD                |
| Low      | 2 BD         | 1 BD           | 5 BD                | 2.5 BD                |

BD = business day (see Definitions below).

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
