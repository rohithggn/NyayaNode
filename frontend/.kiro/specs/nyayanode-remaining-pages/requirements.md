# Requirements Document

## Introduction

NyayaNode is an AI-powered dispute arbitration platform for India's ONDC network. The existing foundation includes a home dashboard, AppShell, Sidebar, TopBar, and mock data. This feature builds out the three remaining pages: a full Disputes list page (`/disputes`), a Cost Analytics Dashboard (`/dashboard`), and an API Log Viewer (`/logs`). All pages must match the established dark legal-tech aesthetic (navy/gold/crimson/emerald palette) and be fully responsive.

## Glossary

- **Dispute**: A consumer complaint filed through the ONDC network between a buyer app, seller app, and logistics provider.
- **DisputeStatus**: One of `Resolved`, `In Progress`, or `Escalated`.
- **CostEvent**: A record of a single AI model invocation including tokens used, cost in INR, and the dispute stage.
- **LogEntry**: A mock API request/response record with timestamp, HTTP method, endpoint, status code, latency, and dispute ID.
- **StatusBadge**: A colour-coded pill component indicating dispute status.
- **DetailPanel**: A modal or slide-over panel showing full dispute details.
- **Stage**: One of `Initial Classification`, `Evidence Analysis`, `Verdict Generation`, or `Full Resolution`.
- **IST**: Indian Standard Time (UTC+5:30).
- **ONDC**: Open Network for Digital Commerce — India's open e-commerce protocol.
- **IGM**: Issue and Grievance Management — the ONDC dispute resolution protocol.

---

## Requirements

### Requirement 1: Disputes List Page (`/disputes`)

**User Story:** As an ONDC network operator, I want to view all disputes in a searchable, filterable table, so that I can quickly locate and review any case.

#### Acceptance Criteria

1. THE Disputes_Page SHALL display a summary row at the top showing total dispute count, resolved count, in-progress count, and escalated count.
2. THE Disputes_Page SHALL render a search bar that filters the disputes table by Case ID, Buyer App, Seller App, or Category as the user types.
3. THE Disputes_Page SHALL render status filter tabs: `All`, `Resolved`, `In Progress`, and `Escalated`.
4. WHEN a filter tab is selected, THE Disputes_Page SHALL display only disputes matching that status.
5. WHEN the search bar contains text, THE Disputes_Page SHALL display only disputes whose Case ID, Buyer App, Seller App, or Category contains the search text (case-insensitive).
6. THE Disputes_Table SHALL display columns: Case ID, Buyer App, Seller App, Amount, Category, Status, Resolution Time, and Action.
7. THE Disputes_Table SHALL format all monetary amounts using `toLocaleString('en-IN')` with INR currency symbol.
8. WHEN a user clicks a table row or the "View" action button, THE Detail_Panel SHALL open and display the full dispute details.
9. THE Detail_Panel SHALL display: Case ID, complaint text, verdict text, Buyer App, Seller App, Logistics App, amount, category, status badge, timestamp, and resolution time.
10. THE Detail_Panel SHALL provide a close mechanism (button or backdrop click) to dismiss it.
11. IF no disputes match the active search and filter combination, THEN THE Disputes_Page SHALL display an empty-state message.

### Requirement 2: Cost Analytics Dashboard (`/dashboard`)

**User Story:** As a platform administrator, I want to see cost analytics for AI model usage, so that I can monitor spending and demonstrate savings versus alternative models.

#### Acceptance Criteria

1. THE Dashboard_Page SHALL display four summary cards: total tokens used, total cost in INR, average cost per dispute, and savings versus GPT-4o.
2. THE Dashboard_Page SHALL render a line chart showing cumulative or per-event cost over time using `costEventLog` timestamps.
3. THE Dashboard_Page SHALL render a bar chart showing total cost grouped by dispute stage (`Initial Classification`, `Evidence Analysis`, `Verdict Generation`, `Full Resolution`).
4. THE Dashboard_Page SHALL render a model comparison table with columns: Model, Tokens Used, Total Cost (INR), Cost per Dispute (INR), and Savings vs GPT-4o.
5. THE Dashboard_Page SHALL include a row for `Gemini Flash 1.5` (actual) and a row for `GPT-4o` (hypothetical baseline) in the comparison table.
6. THE Dashboard_Page SHALL format all INR values using `toLocaleString('en-IN')` with the rupee symbol.
7. WHILE rendering charts, THE Dashboard_Page SHALL use the Recharts library with custom tooltips styled to match the dark theme.
8. THE Dashboard_Page SHALL use `ResponsiveContainer` from Recharts so charts resize correctly on all screen widths.

### Requirement 3: API Log Viewer (`/logs`)

**User Story:** As a developer or system operator, I want to view a real-time API log feed styled like a terminal, so that I can monitor system activity and diagnose issues.

#### Acceptance Criteria

1. THE Logs_Page SHALL render on a dark background (`#0D1117`) with monospace font.
2. THE Logs_Page SHALL display each log entry with: timestamp (IST), HTTP method badge, endpoint path, HTTP status code, latency in milliseconds, and associated dispute ID.
3. THE Logs_Page SHALL colour-code log entries: green (`#10B981`) for 2xx success, red (`#DC2626`) for 4xx/5xx errors, and amber (`#F59E0B`) for warnings (3xx or latency > 1000ms).
4. THE Logs_Page SHALL render filter tabs: `All`, `Success`, `Error`, and `Warning`.
5. WHEN a filter tab is selected, THE Logs_Page SHALL display only log entries matching that level.
6. THE Logs_Page SHALL auto-scroll to the most recent log entry when new entries are appended and auto-scroll is not paused.
7. THE Logs_Page SHALL provide a `Pause` / `Resume` toggle button that stops or resumes auto-scroll.
8. THE mockData module SHALL export at least 20 `LogEntry` records covering a mix of GET and POST methods, 2xx, 4xx, and 5xx status codes, and varying latencies.
9. IF no log entries match the active filter, THEN THE Logs_Page SHALL display an empty-state message within the terminal viewport.

### Requirement 4: Shared Design System Compliance

**User Story:** As a designer, I want all new pages to match the existing NyayaNode design system, so that the product feels cohesive and authoritative.

#### Acceptance Criteria

1. THE new pages SHALL use the colour palette defined in `globals.css`: navy `#0A0F1E`, card `#111827`, border `#1F2937`, gold `#F59E0B`, crimson `#DC2626`, emerald `#10B981`, blue `#3B82F6`.
2. THE new pages SHALL be fully responsive, adapting layout for mobile (< 768px), tablet (768px–1024px), and desktop (> 1024px) viewports.
3. THE new pages SHALL use Tailwind CSS utility classes and inline styles consistent with the existing component patterns.
4. WHERE animations are used, THE new pages SHALL use Framer Motion consistent with the existing codebase.
5. THE new pages SHALL not introduce any new npm dependencies beyond those already installed.
